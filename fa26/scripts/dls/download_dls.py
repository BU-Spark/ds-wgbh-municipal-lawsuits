"""Download DLS General Fund Schedule A exports for FY2002-FY2025.

Install: pip install playwright && python -m playwright install chromium
Run from fa26: python scripts/dls/download_dls.py

Uses the public report UI. Select all 351 municipalities before continuing.
"""
from pathlib import Path
import re
import time
from playwright.sync_api import sync_playwright

URL = 'https://dls-gw.dor.state.ma.us/reports/rdPage.aspx?rdReport=ScheduleA.GeneralFund'
ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'data' / 'raw' / 'dls' / 'schedule_a'
START_YEAR, END_YEAR = 2002, 2025


def select_custom(page, label, value):
    if "Revenues/Expenditures" in label:
        page.locator("#islAmountType").select_option(str(value))
        return

    if "Fiscal Year" in label:
        # Identify the year dropdown from its checkbox options.
        candidates = page.locator(
            'div[data-checkboxlist="True"][data-dropdown="true"]'
        )

        target = None
        for i in range(candidates.count()):
            candidate = candidates.nth(i)
            if candidate.locator(
                f'input[type="checkbox"][value="{value}"]'
            ).count() > 0:
                target = candidate
                break

        if target is None:
            raise RuntimeError(f"Fiscal year {value} not found")

        dropdown_id = target.get_attribute("id")
        trigger = page.locator(f"#{dropdown_id}_handler")

        trigger.click()

        # Clear previously selected years.
        for checkbox in target.locator(
            'input[type="checkbox"]:checked'
        ).all():
            checkbox.uncheck()

        target.locator(
            f'input[type="checkbox"][value="{value}"]'
        ).check()

        trigger.click()

        print(f"Selected FY{value}")
        return

    raise RuntimeError(f"Unknown dropdown: {label}")


def save_export(page, year, kind):
    stem = f'schedule_a_{kind.lower()}_{year}'
    for ext in ('.xls', '.xlsx', '.csv'):
        existing = OUT / (stem + ext)
        if existing.exists() and existing.stat().st_size > 0:
            print('SKIP', existing)
            return
    print(f'Exporting FY{year} {kind}...')
    select_custom(page, 'Select Fiscal Year', year)
    select_custom(page, 'Select Revenues/Expenditures', kind)
    page.get_by_text('Submit', exact=True).click(timeout=15000)
    page.wait_for_load_state('domcontentloaded', timeout=30000)
    with page.expect_download(timeout=60000) as info:
        page.get_by_text('Export to Excel', exact=True).click(timeout=15000)
    download = info.value
    suffix = Path(download.suggested_filename).suffix.lower()
    if suffix not in ('.xls', '.xlsx', '.csv'):
        suffix = '.xls'
    dest = OUT / (stem + suffix)
    download.save_as(dest)
    print('SAVED', dest, dest.stat().st_size, 'bytes')
    time.sleep(1.5)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=120)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()
        page.goto(URL, wait_until='domcontentloaded', timeout=60000)
        print("\nFiscal year control:")
        print(page.locator("text=Select Fiscal Year:").first.evaluate(
            "(el) => el.parentElement.outerHTML.slice(0, 10000)"
        ))

        print("\nCheckboxes:")
        print(page.locator("input[type=checkbox]").count())

        print("\nDropdown elements:")
        for el in page.locator("select, [role=combobox], [role=listbox]").all():
            print(el.evaluate("(e) => e.outerHTML.slice(0, 2000)"))

        # input("Press Enter to exit after inspecting the HTML...")
        # return
    
        print('Opened DLS report. Select all 351 municipalities if needed.')
        input('Confirm all 351 municipalities are selected, then press Enter...')
        for year in range(START_YEAR, END_YEAR + 1):
            for kind in ('Revenues', 'Expenditures'):
                try:
                    save_export(page, year, kind)
                except Exception as exc:
                    print('FAILED', year, kind, repr(exc))
                    page.screenshot(path=str(OUT / f'error_{year}_{kind.lower()}.png'))
                    raise
        browser.close()


if __name__ == '__main__':
    main()
