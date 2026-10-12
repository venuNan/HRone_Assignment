# DECISIONS.md  (about 150-200 words in total - plain language, your own words)

1. **Indexes.** Which indexes did you create, and which query or guarantee does each one serve? Which one did you consider and reject?
I created indexes on the `emp_code` field in both the `employees` and `attendance_logs` collections. Since every employee should have a unique employee code, I created an index on `emp_code` on the `employees` collection unique to prevent duplicate employee records. For `attendance_logs`, I created a compound unique index on `emp_code` and the attendance `date` to prevent duplicate attendance records for the same employee on the same day.These indexes improve query performance as the database grows to 500,000 employees or more.

2. **Punch-in race.** Two identical punch-in requests arrive at the same instant. Walk through exactly what happens in your code.
In punch_in endpoint the punch in race condition is solved by using `insert_one` method for inseritng documents. This ensures when and duplicate document being inserted it throws and duplicate key error becuase of compound index on `emp_code` and `date`.

3. **Ties.** Two employees are tied on late minutes at the cutoff of `limit`. What does your leaderboard return, and why?
This one i didnt do.

4. **Headcount.** How does your department summary make sure employees with zero logs are counted?
This one also i didnt do.

5. **One thing you would change** if this had to serve 100x the data.
I would first changle from `nosql (mongoDB)` to `mysql (MYSQL or postgreSQl)`. Mainly we are having most of the data in same format we are not haivng any different format for each employee so . We here choose mongoDB thinking it gives flexible structure but it gives complexity also when writing queries in the code. We can also track modification in `RDBMS` by saving who modified the attendance_logs. This is the first thing i would change.
