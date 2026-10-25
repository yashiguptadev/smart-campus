# Selenium tests for the Smart Campus Resource Optimizer

Automates test cases TC01–TC12 in Chrome and writes the Lab 12 execution record.

## Run

1. Start the app in one terminal: `python app.py`
2. In a second terminal (venv active), from the project folder:

```
pip install -r tests\requirements-test.txt
python tests\run_campus_tests.py
```

Add `--headless` to run without opening a browser window.
The first run needs internet so Selenium can fetch the Chrome driver.

## Output (in `tests\test_results\`)

- `execution_record.md`: table with actual result and Pass/Fail for each test, ready to paste into the report
- `execution_record.csv`: the same table for Excel
- `screenshots\`: one screenshot per test case

## Notes

- Needs the demo accounts from `seed.py` (student, admin, maintenance).
- The tests create their own bookings and issues on a random free future date, so you can run them again and again.
- Don't click around in the browser window while it runs.
