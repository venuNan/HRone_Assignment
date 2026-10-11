# REVIEW.md

List every defect you found in the starter `app/main.py` (helpers and endpoints). For each one:

| # | Where (function / line) | What is wrong | How you'd notice it (test, input, or symptom) | How you fixed it |
|---|-------------------------|---------------|-----------------------------------------------|------------------|
| 1 |Health endpoint| The health endpoint returned a predefined JSON response without checking whether MongoDB was running or accessible.|The endpoint returned a healthy status even when MongoDB was down or unreachable. |Modified the health endpoint to check MongoDB connectivity and report the service status based on whether the database is accessible.|



Also note anything you looked at and decided was **not** a defect, and why.
