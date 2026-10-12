"""
Employee Attendance & Analytics API - STARTER

Run:  uvicorn app.main:app --port 8000
Env:  MONGO_URI, MONGO_DB (a local .env is loaded for convenience)

This file was written quickly by a colleague who has left the company. The happy path
works, but nobody has reviewed it. Read PROBLEM_STATEMENT.docx for what is expected of you,
openapi.yaml for the contract and DATA_MODEL.md for what is stored in MongoDB.
"""
import os
from datetime import datetime, timedelta, timezone, date
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel
from pymongo import MongoClient, ReturnDocument
from pymongo.errors import ConnectionFailure, DuplicateKeyError
import calendar

load_dotenv()

client = MongoClient(os.getenv("MONGO_URI", "mongodb://localhost:27017"))
db = client[os.getenv("MONGO_DB", "attendance_db")]

IST = timezone(timedelta(hours=5, minutes=30))

app = FastAPI(title="Employee Attendance & Analytics API", version="2.0.0")


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def compute_late_minutes(punch_in: datetime, shift_start: str) -> int:
    h, m = map(int, shift_start.split(":"))
    start = punch_in.replace(hour=h, minute=m, second=0, microsecond=0)
    minutes = int((punch_in - start).total_seconds() / 60)
    return minutes if minutes > 10 else 0


def compute_work_hours(punch_in: datetime, punch_out: datetime) -> float:
    return round((punch_out - punch_in).total_seconds() / 3600, 2)


def compute_overtime(punch_out: datetime, shift_end: str, date_str: str) -> int:
    h, m = map(int, shift_end.split(":"))
    end = datetime.fromisoformat(date_str).replace(hour=h, minute=m, tzinfo=IST)
    return max(0, int((punch_out - end).total_seconds() / 60))


# --------------------------------------------------------------------------- #
# Models
# --------------------------------------------------------------------------- #
class EmployeeIn(BaseModel):
    emp_code: str
    name: str
    email: str
    department: str
    shift_start: str = "09:30"
    shift_end: str = "18:30"
    joined_on: str


class PunchInIn(BaseModel):
    emp_code: str
    punched_at: Optional[int] = None
    status: str = "PRESENT"


# --------------------------------------------------------------------------- #
# Endpoints provided
# --------------------------------------------------------------------------- #
@app.get("/health", status_code=200)  # defect 1
def health():
    try:
        response = client.admin.command('ping')
        
        if response.get("ok") == 1.0:
            return {"detail":"MongoDB status: HEALTHY"}
    except ConnectionFailure:
        raise HTTPException(500, detail="MongoDB status: UNHEALTHY (Cant connect to the MONGODB).")
        return False
    except Exception as e:
        raise HTTPException(500, detail="MongoDB status: UNHEALTHY (Error: {e}).")


@app.post("/employees", status_code=201)
def create_employee(body: EmployeeIn):
    if db.employees.find_one({"emp_code": body.emp_code}):
        raise HTTPException(409, "Employee with emp_code already exists")
    doc = body.model_dump()
    doc["created_at"] = datetime.now()
    db.employees.insert_one(doc)
    doc.pop("_id", None)
    return doc


@app.get("/employees")
def list_employees(department: Optional[str] = None, page: int = 1, page_size: int = 20):
    q = {}
    if department:
        q["department"] = department
    skip = (page-1) * page_size
    total = db.employees.count_documents(q)
    items = list(db.employees.find(q, {"_id": 0}).skip(skip).limit(page_size))
    return {"items": items, "total": total, "page": page, "page_size": page_size}

@app.get("/attendance")
def list_attendance(
    emp_code: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    status: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
):
    q = {}
    if emp_code:
        q["emp_code"] = emp_code
    if date_from or date_to:
        q["date"] = {}
        if date_from:
            q["date"]["$gte"] = date_from
        if date_to:
            q["date"]["$lte"] = date_to
    if status:
        q["status"] = status
    docs = list(db.attendance_logs.find(q))
    docs.sort(key=lambda d: d["date"], reverse=True)
    total = len(docs)
    page_docs = docs[(page - 1) * page_size : page * page_size]
    for d in page_docs:
        d["id"] = str(d.pop("_id"))
    return {"items": page_docs, "total": total, "page": page, "page_size": page_size}


@app.post("/attendance/punch-in", status_code=201)
def punch_in(body: PunchInIn):
    emp = db.employees.find_one({"emp_code": body.emp_code})
    if not emp: # defect 4
        raise HTTPException(404, detail="Employee unknown or doesnt exist.")
    
    ts = datetime.fromtimestamp(body.punched_at / 1000) if body.punched_at else datetime.now()
    d = ts.date().isoformat()

    if db.attendance_logs.find_one({"emp_code": body.emp_code, "date": d}):
        raise HTTPException(409, "already punched in for this date")
    
    late_minutes = compute_late_minutes(ts, emp["shift_start"])
    doc = {
        "emp_code": body.emp_code,
        "date": d,
        "status": body.status,
        "punch_in": ts,
        "punch_out": None,
        "work_hours": None,
        "late_minutes": 0 if late_minutes <= 10 else late_minutes,
        "overtime_minutes": 0,
        "half_day": False,
        "history": [],
    }
    try:
        res = db.attendance_logs.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(409, detail="already punched in for this date")
    
    doc["id"] = str(res.inserted_id)
    doc.pop("_id", None)
    return doc


@app.post("/attendance/punch-out", status_code=201)
def punch_out(body: PunchInIn):
    emp = db.employees.find_one({"emp_code": body.emp_code})

    if not emp:
        raise HTTPException(404, detail="Employee unknown or doesnt exist.")

    ts = datetime.fromtimestamp(body.punched_at / 1000) if body.punched_at else datetime.now()
    d = ts.date().isoformat()

    attendance = db.attendance_logs.find_one(
        {
            "emp_code":body.emp_code,
            "date":d,
            "punch_in":{"$exists":True},
            "punch_out": None
        }
    )

    if not attendance:
        raise HTTPException(409, detail="Employee did not punchedIn or already PunchedOut")
    
    if ts <= attendance["punch_in"] or ts > attendance["punch_in"] + timedelta(hours=24):
        raise HTTPException(
            status_code=422,
            detail="Punch-out time must be after punch-in and within 24 hours of it."
        )

    work_hours = compute_work_hours(ts, attendance["punch_in"])
    over_time = compute_overtime(ts, emp["shift_end"])
    attendance_update = db.attendance_logs.find_one_and_update(
        {
            "emp_code":body.emp_code,
            "date":d,
            "punch_in": {"$exists": True},
            "punch_out": None
            
        },
        {
            "$set":{
                "punch_out":ts,
                "work_hours": work_hours,
                "overtime_minutes":over_time if over_time >= 30 else 0,
                "half_day": work_hours < 4.50

            }
        },
        return_document= ReturnDocument.AFTER
    )

    if not attendance_update:
        raise HTTPException(409, detail="Employee did not punchedIn or already PunchedOut")
    

    attendance_update["id"] = str(attendance_update["_id"])
    attendance_update.pop("_id", None)

    return attendance_update

@app.patch("/attendance/{emp_code}/{date}")
def regularizeAttendance(emp_code: str, date: str):
    emp = db.employees.find_one({"emp_code":emp_code})
    if not emp:
        raise HTTPException(404, detail="Unknown employee.")

    return {"detail":" I didnt understood this point so thank you."}

    
@app.get("/analytics/employees/{emp_code}/monthly", status_code=200)
def employee_monthly(emp_code: str):
    emp = db.employees.find_one({"emp_code":emp_code})
    if not emp:
        raise HTTPException(404, detail="Unknown employee.")



    aggregate_pipeline: list = [
        {
            "$group": {
                "_id": {
                    "emp_code": "$emp_code",
                    "year": {
                        "$year": {
                            "$dateFromString": {
                                "dateString": "$date",
                                "format": "%Y-%m-%d"
                            }
                        }
                    },
                    "month": {
                        "$month": {
                            "$dateFromString": {
                                "dateString": "$date",
                                "format": "%Y-%m-%d"
                            }
                        }
                    }
                },

                "present_days": {
                    "$sum": {
                        "$cond": [
                            {
                                "$and": [
                                    {"$eq": ["$status", "Present"]},
                                    {
                                        "$in": [
                                            {
                                                "$dayOfWeek": {
                                                    "$dateFromString": {
                                                        "dateString": "$date",
                                                        "format": "%Y-%m-%d"
                                                    }
                                                }
                                            },
                                            [2, 3, 4, 5, 6]
                                        ]
                                    }
                                ]
                            },
                            1,
                            0
                        ]
                    }
                },

                "leave_days": {
                    "$sum": {
                        "$cond": [
                            {"$eq": ["$status", "Leave"]},
                            1,
                            0
                        ]
                    }
                },

                "late_count": {
                    "$sum": {
                        "$cond": [
                            {"$gt": ["$late_minutes", 0]},
                            1,
                            0
                        ]
                    }
                },

                "total_late_minutes": {"$sum": "$late_minutes"},
                "total_overtime": {"$sum": "$overtime_minutes"}
            }
        },
        {
            "$sort": {
                "_id.year": 1,
                "_id.month": 1,
                "_id.emp_code": 1
            }
        }
    ]

    results = db.attendance_logs.aggregate(aggregate_pipeline)

    for document in results:
        emp_code = document["_id"]["emp_code"]
        year = document["_id"]["year"]
        month = document["_id"]["month"]

        employee = db.employees.find_one(
            {"emp_code": emp_code},
            {"joined_on": 1}
        )

        if not employee or not employee.get("joined_on"):
            continue

        joined_on = date.fromisoformat(employee["joined_on"])

        # First and last day of the report month
        month_start = date(year, month, 1)
        month_end = date(year, month, calendar.monthrange(year, month)[1])

        # Start counting from the later of joined_on or month_start
        start_date = max(joined_on, month_start)

        working_days = 0

        if start_date <= month_end:
            for day in range((month_end - start_date).days + 1):
                current_date = start_date.fromordinal(
                    start_date.toordinal() + day
                )

                # Monday = 0, Sunday = 6
                if current_date.weekday() < 5:
                    working_days += 1

        present_days = document["present_days"]

        attendance_pct = (
            round((present_days / working_days) * 100, 2)
            if working_days > 0
            else 0
        )

        document["working_days"] = working_days
        document["attendance_pct"] = attendance_pct
        # The above one is also written AI

        return {"detail":" I tried but i couldnt do it. I am using more AI so it didnt feel good. Normally my tech stack is flask and SQL, MYSQL, PostgreSQL. I undestand mongoDB but when it comes to aggregate it became complex. So if its ok i am just asking for another chance. Dont think i quit in the middle. I tried but it became too complex  because doing all this using documentation is good but became a headache. Thank you please."}
        
        
@app.get("/analytics/departments/summary")
def department_summary():
    pass

@app.get("/analytics/leaderboard/late")
def late_leaderboard():
    pass


@app.get("/analytics/departments/{department}/trend")
def department_trend(department: str):
    pass

@app.get("/admin/explain/{endpoint}")
def explain_endpoint(endpoint: str):
    pass







# --------------------------------------------------------------------------- #
# TODO - the rest of the contract (see openapi.yaml):
#   POST  /attendance/punch-out
#   PATCH /attendance/{emp_code}/{date}
#   GET   /analytics/employees/{emp_code}/monthly
#   GET   /analytics/departments/summary
#   GET   /analytics/leaderboard/late
#   GET   /analytics/departments/{department}/trend
#   GET   /admin/explain/{endpoint}
# --------------------------------------------------------------------------- #
