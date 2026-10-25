#!/usr/bin/env python3
"""Selenium test suite for the Smart Campus Resource Optimizer (TC01-TC12).

It drives a real Chrome browser against the running app, performs each test case
through the web interface, and writes an execution record with the actual results
and a screenshot per test case.

Usage (app must already be running in another terminal):
    python run_campus_tests.py
    python run_campus_tests.py --headless
    python run_campus_tests.py --base-url http://127.0.0.1:5000
    (for a deployed site, set ADMIN_PASSWORD / MAINT_PASSWORD in the terminal first
     if you changed them, then pass --base-url https://your-app.onrender.com)

The tests create their own bookings and issues, on a free future date picked at
random, so they can be run repeatedly. They rely on the demo accounts created by
seed.py.
"""
import argparse
import csv
import os
import random
import re
import sys
import time
import urllib.request
from datetime import date, datetime, timedelta

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait

USERS = {
    "student": ("student@muj.edu", "Stu@123"),
    "admin": ("admin@muj.edu", os.environ.get("ADMIN_PASSWORD", "Admin@123")),
    "maintenance": ("maintenance@muj.edu", os.environ.get("MAINT_PASSWORD", "Maint@123")),
}
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_results")
TEST_HOURS = (10, 12, 14, 16)  # slots the tests book on the chosen day


def fmt(day):
    """Date as the app shows it in tables, e.g. 03 Nov 2026."""
    return day.strftime("%d %b %Y")


class Ctx:
    """Browser plus the small amount of state shared between test cases."""

    def __init__(self, driver, base):
        self.driver = driver
        self.base = base.rstrip("/")
        self.wait = WebDriverWait(driver, 10)
        self.role = None
        self.rid = None  # Computer Lab resource id
        self.day = None  # free future date used for bookings
        self.codes = {}

    # ---------------------------------------------------------- basics
    def url(self, path):
        return self.base + path

    def submit(self, button):
        """Click a submit button and wait for the next page to load."""
        button.click()
        self.wait.until(EC.staleness_of(button))

    def submit_confirm(self, button):
        """Click a button that opens a JavaScript confirm() dialog and accept it."""
        button.click()
        self.wait.until(EC.alert_is_present())
        self.driver.switch_to.alert.accept()
        self.wait.until(EC.staleness_of(button))

    def read_flash(self):
        """Return (kind, text) of the message shown after an action."""

        def find(d):
            for kind in ("success", "danger", "warning", "info"):
                els = d.find_elements(By.ID, f"flash-{kind}")
                if els:
                    return kind, els[0].text
            return False

        return self.wait.until(find)

    # ----------------------------------------------------------- login
    def login(self, role):
        email, password = USERS[role]
        d = self.driver
        d.get(self.url("/login"))
        d.delete_all_cookies()
        d.get(self.url("/login"))
        self.wait.until(EC.visibility_of_element_located((By.ID, "email"))).send_keys(email)
        d.find_element(By.ID, "password").send_keys(password)
        self.submit(d.find_element(By.ID, "login-button"))
        self.wait.until(EC.visibility_of_element_located((By.ID, "dashboard")))
        self.role = role

    def ensure(self, role):
        if self.role != role:
            self.login(role)

    # ------------------------------------------------------- resources
    def search(self, name):
        d = self.driver
        d.find_element(By.LINK_TEXT, "Resources").click()
        box = self.wait.until(EC.visibility_of_element_located((By.ID, "search")))
        box.clear()
        box.send_keys(name)
        self.submit(d.find_element(By.ID, "search-button"))
        self.wait.until(EC.presence_of_element_located((By.ID, "resource-list")))

    def slot(self, hour):
        self.wait.until(EC.presence_of_element_located((By.ID, "slots")))
        return self.driver.find_element(
            By.XPATH,
            f"//div[@id='slots']/*[starts-with(normalize-space(span[@class='slot-time']), '{hour:02d}:00')]",
        )

    def find_free_day(self):
        """Pick a future date where all hours the tests use are free."""
        d = self.driver
        for _ in range(40):
            candidate = date.today() + timedelta(days=random.randint(40, 400))
            d.get(self.url(f"/resources/{self.rid}?date={candidate.isoformat()}"))
            if all(self.slot(h).get_attribute("data-state") == "free" for h in TEST_HOURS):
                return candidate
        raise AssertionError("Could not find a free date for the test bookings")

    def pick_date(self, day):
        d = self.driver
        field = self.wait.until(EC.presence_of_element_located((By.ID, "date")))
        d.execute_script("arguments[0].value = arguments[1];", field, day.isoformat())
        self.submit(d.find_element(By.ID, "check-button"))
        self.wait.until(EC.presence_of_element_located((By.ID, "slots")))
        assert day.isoformat() in d.current_url, "Date was not applied"

    def open_computer_lab_on_test_day(self):
        """Login must already be done. Search, open Computer Lab, pick the test date."""
        d = self.driver
        d.get(self.url("/dashboard"))
        self.search("Computer Lab")
        d.find_element(By.LINK_TEXT, "Computer Lab").click()
        self.wait.until(EC.presence_of_element_located((By.ID, "slots")))
        self.rid = int(re.search(r"/resources/(\d+)", d.current_url).group(1))
        if self.day is None:
            self.day = self.find_free_day()
        self.pick_date(self.day)

    # -------------------------------------------------------- bookings
    def book(self, start_hour, end_hour, purpose):
        """Fill in and submit the booking form. Returns (kind, message)."""
        d = self.driver
        d.get(
            self.url(
                f"/bookings/new?resource_id={self.rid}&date={self.day.isoformat()}&start={start_hour:02d}:00"
            )
        )
        Select(self.wait.until(EC.presence_of_element_located((By.ID, "start")))).select_by_value(
            f"{start_hour:02d}:00"
        )
        Select(d.find_element(By.ID, "end")).select_by_value(f"{end_hour:02d}:00")
        d.find_element(By.ID, "purpose").send_keys(purpose)
        self.submit(d.find_element(By.ID, "submit-booking"))
        return self.read_flash()

    def book_ok(self, start_hour, end_hour, purpose):
        kind, text = self.book(start_hour, end_hour, purpose)
        assert kind == "success", f"Booking was not created: {text}"
        return re.search(r"\bB\d+\b", text).group()

    def my_booking_row(self, code):
        self.driver.get(self.url("/bookings/"))
        return self.wait.until(
            EC.presence_of_element_located((By.XPATH, f"//tr[td[1][normalize-space()='{code}']]"))
        )

    def admin_status_row(self, code, status):
        self.driver.get(self.url(f"/admin/bookings?status={status}"))
        return self.wait.until(EC.presence_of_element_located((By.XPATH, f"//tr[@data-booking='{code}']")))


# ===================================================================== tests
def tc01(c):
    d = c.driver
    d.get(c.url("/login"))
    d.delete_all_cookies()
    d.get(c.url("/login"))
    c.wait.until(EC.visibility_of_element_located((By.ID, "email"))).send_keys(USERS["student"][0])
    d.find_element(By.ID, "password").send_keys(USERS["student"][1])
    c.submit(d.find_element(By.ID, "login-button"))
    dash = c.wait.until(EC.visibility_of_element_located((By.ID, "dashboard")))
    assert "/dashboard" in d.current_url, f"Unexpected page: {d.current_url}"
    c.role = "student"
    return f"Logged in; dashboard displayed ('{dash.find_element(By.TAG_NAME, 'h1').text}')"


def tc02(c):
    d = c.driver
    d.get(c.url("/login"))
    d.delete_all_cookies()
    d.get(c.url("/login"))
    c.role = None
    c.wait.until(EC.visibility_of_element_located((By.ID, "email"))).send_keys(USERS["student"][0])
    d.find_element(By.ID, "password").send_keys("wrong123")
    c.submit(d.find_element(By.ID, "login-button"))
    kind, text = c.read_flash()
    assert kind == "danger", f"No error message shown (got {kind}: {text})"
    assert not d.find_elements(By.ID, "dashboard"), "Dashboard was shown after a wrong password"
    assert "/login" in d.current_url, f"Left the login page: {d.current_url}"
    return f"Login rejected; error shown: '{text}'"


def tc03(c):
    c.ensure("student")
    c.driver.get(c.url("/dashboard"))
    c.search("Computer Lab")
    links = [a.text for a in c.driver.find_elements(By.CSS_SELECTOR, "#resource-list tbody a")]
    assert "Computer Lab" in links, f"Computer Lab not in results: {links}"
    return f"Search returned {len(links)} result(s); Computer Lab displayed"


def tc04(c):
    c.ensure("student")
    c.open_computer_lab_on_test_day()
    states = [c.slot(h).get_attribute("data-state") for h in range(8, 18)]
    free = states.count("free")
    assert free >= 1, f"No free slots shown: {states}"
    return f"{free} of {len(states)} slots shown as free on {fmt(c.day)}"


def tc05(c):
    c.ensure("student")
    c.open_computer_lab_on_test_day()
    link = c.driver.find_element(
        By.XPATH,
        "//a[contains(@class,'slot-link')][starts-with(normalize-space(span[@class='slot-time']),'10:00')]",
    )
    link.click()
    c.wait.until(EC.presence_of_element_located((By.ID, "submit-booking")))
    c.driver.find_element(By.ID, "purpose").send_keys("Project Work")
    c.submit(c.driver.find_element(By.ID, "submit-booking"))
    kind, text = c.read_flash()
    assert kind == "success", f"Booking request not created: {text}"
    code = re.search(r"\bB\d+\b", text).group()
    c.codes["tc05"] = code
    row = c.my_booking_row(code)
    status = row.find_element(By.CSS_SELECTOR, ".status").text
    assert status == "Pending", f"Expected Pending, found {status}"
    return f"Booking request {code} created for 10:00-11:00 on {fmt(c.day)}; status {status}"


def tc06(c):
    c.ensure("student")
    c.open_computer_lab_on_test_day()
    state = c.slot(10).get_attribute("data-state")
    assert state == "booked", f"Precondition failed: 10:00 slot is '{state}' (run TC05 first)"
    kind, text = c.book(10, 11, "Overlapping booking")
    assert kind == "danger" and "unavailable" in text.lower(), f"Conflict not reported: {kind}: {text}"
    shot_text = text
    c.driver.get(c.url("/bookings/"))
    rows = c.driver.find_elements(
        By.XPATH,
        f"//tr[td[3][normalize-space()='{fmt(c.day)}'] and starts-with(normalize-space(td[4]),'10:00')]",
    )
    assert len(rows) == 1, f"Expected 1 booking for the slot, found {len(rows)}"
    return f"Conflicting booking prevented: '{shot_text[:90]}'; existing booking unchanged"


def tc07(c):
    c.ensure("student")
    c.open_computer_lab_on_test_day()
    code = c.book_ok(12, 13, "Booking to cancel")
    row = c.my_booking_row(code)
    c.submit_confirm(row.find_element(By.XPATH, ".//button[normalize-space()='Cancel booking']"))
    kind, text = c.read_flash()
    assert kind == "success" and "cancelled" in text.lower(), f"Cancellation not confirmed: {kind}: {text}"
    status = c.my_booking_row(code).find_element(By.CSS_SELECTOR, ".status").text
    assert status == "Cancelled", f"Expected Cancelled, found {status}"
    c.driver.get(c.url(f"/resources/{c.rid}?date={c.day.isoformat()}"))
    state = c.slot(12).get_attribute("data-state")
    assert state == "free", f"Slot was not released (state: {state})"
    c.driver.get(c.url("/bookings/"))
    return f"Booking {code} cancelled; 12:00 slot is free again"


def tc08(c):
    c.ensure("student")
    c.open_computer_lab_on_test_day()
    code = c.book_ok(14, 15, "Booking to approve")
    c.codes["approved"] = code
    c.login("admin")
    c.driver.find_element(By.LINK_TEXT, "Requests").click()
    c.wait.until(EC.presence_of_element_located((By.ID, "booking-queue")))
    row = c.admin_status_row(code, "pending")
    c.submit(row.find_element(By.XPATH, ".//button[normalize-space()='Approve']"))
    kind, text = c.read_flash()
    assert kind == "success" and "approved" in text.lower(), f"Approval not confirmed: {kind}: {text}"
    status = c.admin_status_row(code, "approved").find_element(By.CSS_SELECTOR, ".status").text
    assert status == "Approved", f"Expected Approved, found {status}"
    return f"Booking {code} status changed from Pending to {status}"


def tc09(c):
    c.ensure("student")
    c.driver.get(c.url("/dashboard"))
    c.search("Projector")
    c.driver.find_element(By.LINK_TEXT, "Projector").click()
    c.wait.until(EC.element_to_be_clickable((By.LINK_TEXT, "Report a problem with this resource"))).click()
    chosen = Select(c.wait.until(EC.presence_of_element_located((By.ID, "resource_id"))))
    assert chosen.first_selected_option.text == "Projector", "Projector was not preselected"
    c.driver.find_element(By.ID, "description").send_keys(
        f"Projector not working (automated test {datetime.now():%H:%M:%S})"
    )
    c.submit(c.driver.find_element(By.ID, "submit-issue"))
    kind, text = c.read_flash()
    assert kind == "success", f"Issue not recorded: {text}"
    code = re.search(r"\bI\d+\b", text).group()
    c.codes["issue"] = code
    row = c.wait.until(EC.presence_of_element_located((By.XPATH, f"//tr[@data-issue='{code}']")))
    status = row.find_element(By.CSS_SELECTOR, ".status").text
    assert status == "Open", f"Expected Open, found {status}"
    return f"Issue {code} recorded for Projector; status {status}"


def tc10(c):
    code = c.codes.get("issue")
    assert code, "No issue available (TC09 must run first)"
    c.login("maintenance")
    c.driver.find_element(By.LINK_TEXT, "Issues").click()
    row = c.wait.until(EC.presence_of_element_located((By.XPATH, f"//tr[@data-issue='{code}']")))
    c.submit(row.find_element(By.XPATH, ".//button[normalize-space()='Mark resolved']"))
    kind, text = c.read_flash()
    assert kind == "success" and "resolved" in text.lower(), f"Resolution not confirmed: {kind}: {text}"
    c.driver.get(c.url("/issues/?status=resolved"))
    row = c.wait.until(EC.presence_of_element_located((By.XPATH, f"//tr[@data-issue='{code}']")))
    status = row.find_element(By.CSS_SELECTOR, ".status").text
    assert status == "Resolved", f"Expected Resolved, found {status}"
    c.driver.get(c.url("/resources/?q=Projector"))
    res_status = c.wait.until(
        EC.presence_of_element_located(
            (By.XPATH, "//tr[td/a[normalize-space()='Projector']]//span[contains(@class,'status')]")
        )
    ).text
    if "available again" in text:
        assert res_status == "Available", f"Resource should be Available, found {res_status}"
    else:
        assert res_status == "Under maintenance", f"Resource status inconsistent: {res_status}"
    return f"Issue {code} marked Resolved; Projector now shows '{res_status}'"


def tc12(c):
    code = c.codes.get("approved")
    assert code, "No approved booking available (TC08 must run first)"
    c.login("student")
    badge = c.driver.find_elements(By.ID, "notif-count")
    assert badge, "No unread-notification badge shown after login"
    unread = badge[0].text
    c.driver.find_element(By.ID, "notifications-link").click()
    c.wait.until(EC.presence_of_element_located((By.ID, "notification-list")))
    item = c.driver.find_element(
        By.XPATH, f"//li[contains(., 'booking {code} for') and contains(., 'approved')]"
    )
    return f"Notification received ({unread} unread): '{item.find_element(By.CLASS_NAME, 'notif-message').text[:100]}'"


def tc11(c):
    c.ensure("student")
    c.open_computer_lab_on_test_day()
    code = c.book_ok(16, 17, "Booking to reject")
    c.codes["rejected"] = code
    c.login("admin")
    c.driver.find_element(By.LINK_TEXT, "Requests").click()
    c.wait.until(EC.presence_of_element_located((By.ID, "booking-queue")))
    row = c.admin_status_row(code, "pending")
    c.submit_confirm(row.find_element(By.XPATH, ".//button[normalize-space()='Reject']"))
    kind, text = c.read_flash()
    assert kind == "success" and "rejected" in text.lower(), f"Rejection not confirmed: {kind}: {text}"
    status = c.admin_status_row(code, "rejected").find_element(By.CSS_SELECTOR, ".status").text
    assert status == "Rejected", f"Expected Rejected, found {status}"
    return f"Booking {code} status changed from Pending to {status}"


# (id, scenario, test data, expected result, function). TC11 runs before TC12 so the
# student has both an approval and a rejection to be notified about.
TESTS = [
    ("TC01", "Login with valid credentials", "Email: student@muj.edu; Password: Stu@123",
     "User should login successfully", tc01),
    ("TC02", "Login with invalid credentials", "Email: student@muj.edu; Password: wrong123",
     "Login denied and error displayed", tc02),
    ("TC03", "Search for an existing resource", "Resource: Computer Lab",
     "Matching resource should be displayed", tc03),
    ("TC04", "Check resource availability", "Computer Lab; auto-selected free future date",
     "Available time slots should be displayed", tc04),
    ("TC05", "Book an available resource", "Computer Lab; 10:00-11:00; Purpose: Project Work",
     "Booking request should be created", tc05),
    ("TC06", "Attempt overlapping booking", "Computer Lab; occupied slot 10:00-11:00",
     "System should prevent conflicting booking", tc06),
    ("TC07", "Cancel an existing booking", "Student's own booking, 12:00-13:00",
     "Booking should be cancelled and resource released", tc07),
    ("TC08", "Administrator approves booking", "New pending booking, 14:00-15:00; Approve",
     "Booking status should become Approved", tc08),
    ("TC09", "Report an issue with a resource", "Projector; Not Working",
     "Issue should be recorded for maintenance", tc09),
    ("TC10", "Maintenance staff resolves issue", "Issue from TC09; Resolved",
     "Issue/resource status should be updated", tc10),
    ("TC11", "Administrator rejects booking", "New pending booking, 16:00-17:00; Reject",
     "Booking status should become Rejected", tc11),
    ("TC12", "Check booking notification", "Booking approved in TC08",
     "User should receive status notification", tc12),
]


# =================================================================== runner
def short(exc):
    first = (str(exc) or type(exc).__name__).strip().split("\n")[0]
    first = re.sub(r"\s+", " ", first)
    return (type(exc).__name__ + ": " + first)[:300]


def clear_alert(driver):
    try:
        driver.switch_to.alert.dismiss()
    except Exception:
        pass


def write_reports(results, base, browser):
    os.makedirs(OUT_DIR, exist_ok=True)
    passed = sum(1 for r in results if r["status"] == "Pass")
    total = len(results)
    pct = round(100 * passed / total) if total else 0

    with open(os.path.join(OUT_DIR, "execution_record.csv"), "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["Test ID", "Test scenario", "Test data", "Expected result", "Actual result", "Status", "Screenshot"])
        for r in results:
            w.writerow([r["id"], r["scenario"], r["data"], r["expected"], r["actual"], r["status"], r["shot"]])

    def cell(text):
        return str(text).replace("|", "/").replace("\n", " ")

    lines = [
        "# Execution record: Smart Campus Resource Optimizer",
        "",
        f"- Run: {datetime.now():%d %b %Y, %H:%M}",
        f"- Application: {base}",
        f"- Browser: {browser}; tool: Selenium WebDriver (Python)",
        "",
        "| Test ID | Scenario | Test data | Expected result | Actual result | Status |",
        "|---|---|---|---|---|---|",
    ]
    for r in results:
        lines.append(
            f"| {r['id']} | {cell(r['scenario'])} | {cell(r['data'])} | {cell(r['expected'])} | "
            f"{cell(r['actual'])} | {r['status']} |"
        )
    lines += ["", f"Total: {total}; Passed: {passed}; Failed: {total - passed}; Pass percentage: {pct}%", ""]
    with open(os.path.join(OUT_DIR, "execution_record.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    return passed, total, pct


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", default="http://127.0.0.1:5000")
    parser.add_argument("--headless", action="store_true", help="run Chrome without opening a window")
    args = parser.parse_args()

    try:
        # generous timeout: a free host that was asleep needs about a minute to wake up
        urllib.request.urlopen(args.base_url.rstrip("/") + "/login", timeout=120)
    except Exception as exc:
        sys.exit(f"Can't reach the app at {args.base_url} ({exc}).\nStart it first with: python app.py")

    options = webdriver.ChromeOptions()
    options.add_argument("--window-size=1366,900")
    if args.headless:
        options.add_argument("--headless=new")
    driver = webdriver.Chrome(options=options)
    if not args.headless:
        driver.maximize_window()
    browser = f"Chrome {driver.capabilities.get('browserVersion', '')}".strip()

    os.makedirs(os.path.join(OUT_DIR, "screenshots"), exist_ok=True)
    ctx = Ctx(driver, args.base_url)
    results = []
    try:
        for tid, scenario, data, expected, fn in TESTS:
            try:
                actual, status = fn(ctx), "Pass"
            except Exception as exc:  # a failed assertion or a missing page element
                actual, status = short(exc), "Fail"
            clear_alert(driver)
            shot = os.path.join("screenshots", f"{tid}_{status}.png")
            try:
                driver.save_screenshot(os.path.join(OUT_DIR, shot))
            except Exception:
                shot = ""
            print(f"{tid}  {status.upper():4}  {scenario}\n        {actual}")
            results.append(dict(id=tid, scenario=scenario, data=data, expected=expected,
                                actual=actual, status=status, shot=shot))
    finally:
        driver.quit()

    passed, total, pct = write_reports(results, args.base_url, browser)
    print(f"\nTotal: {total}  Passed: {passed}  Failed: {total - passed}  Pass percentage: {pct}%")
    print(f"Execution record and screenshots saved in: {OUT_DIR}")
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
