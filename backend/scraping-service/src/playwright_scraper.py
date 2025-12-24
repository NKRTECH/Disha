import time
import re
import base64
from typing import List, Dict, Optional, Set
from playwright.sync_api import sync_playwright, Page, Locator, Browser, BrowserContext, Playwright
from src.utils import clean_text, append_to_csv, append_to_jsonl
from src.config import (
    HEADLESS,
    LOGIN_EMAIL,
    LOGIN_PASSWORD,
    MAIN_URL,
    COLLEGE_SEARCH_URL,
    MAX_SCROLLS,
    SCROLL_PAUSE_TIME,
    MAX_PAGES,
)
from src.logger import setup_logger

logger = setup_logger()

class PlaywrightScraper:
    def __init__(self):
        self.playwright: Optional[Playwright] = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.colleges_data = []
        self.last_new_records = 0
        self.last_total_cards = 0

    @staticmethod
    def _extract_course_details_from_card(card: Locator) -> Dict:
        # Build dictionary in Selenium order: Course Name, Fees, Duration, Degree Type, Entrance Exams
        # Note: Course Name will be added by the caller
        # Always include all fields (with empty string if missing) to match Selenium structure
        
        fees = ""
        duration = ""
        degree_type = ""
        entrance_exams = ""
        
        # 1. Extract Fees
        # Strategy A: Look for the Indian Rupee icon (fa-indian-rupee-sign)
        try:
            rupee_icon = card.locator(".college-basic-details i.fa-indian-rupee-sign").first
            if rupee_icon.count() > 0:
                # The text is in the parent <li>
                fees_text = rupee_icon.locator("xpath=..").text_content()
                # Clean up artifacts like 'Fetch fees' which might be present in the DOM
                fees = fees_text.replace('₹', '').replace('Fetch fees', '').strip()
        except Exception as e:
            logger.warning(f"Failed to extract fees via icon: {e}")

        # Strategy B: Fallback to 'li.current-fees' class
        if not fees:
            try:
                if card.locator("li.current-fees").count() > 0:
                    fees = card.locator("li.current-fees").first.text_content().replace('₹', '').strip()
            except Exception as e:
                logger.warning(f"Failed to extract fees via class: {e}")

        # 2. Extract Duration (fa-calendar-days)
        try:
            icon = card.locator(".college-basic-details i.fa-calendar-days").first
            if icon.count() > 0:
                duration = icon.locator("xpath=..").text_content().strip()
        except Exception as e:
            logger.warning(f"Failed to extract duration via icon: {e}")

        # 3. Extract Degree Type (fa-chart-simple)
        try:
            icon = card.locator(".college-basic-details i.fa-chart-simple").first
            if icon.count() > 0:
                degree_type = icon.locator("xpath=..").text_content().strip()
        except Exception as e:
            logger.warning(f"Failed to extract degree type via icon: {e}")

        # 4. Extract Entrance Exams (fa-pen)
        try:
            icon = card.locator(".college-basic-details i.fa-pen").first
            if icon.count() > 0:
                raw_text = icon.locator("xpath=..").text_content().strip()
                entrance_exams = raw_text.replace("Exams:", "").strip()
        except Exception as e:
            logger.warning(f"Failed to extract entrance exams via icon: {e}")

        # Fallback: Iterate all LIs if any field is still missing
        if not (duration and degree_type and entrance_exams):
            try:
                lis = card.locator("li").all()
                for li in lis:
                    txt = li.text_content().strip()
                    if not duration and "year" in txt.lower():
                        duration = txt
                    elif not degree_type and "degree" in txt.lower():
                        degree_type = txt
                    elif not entrance_exams and "exam" in txt.lower():
                        entrance_exams = txt.replace("Exams:", "").strip()
            except Exception as e:
                logger.warning(f"Failed to extract other course details (fallback): {e}")

        details = {
            "Fees": fees,
            "Duration": duration,
            "Degree Type": degree_type,
            "Entrance Exams": entrance_exams
        }

        return details

    def _extract_courses_via_dom(self, card: Locator, page: Page) -> List[Dict]:
        courses = []
        btn = card.locator("button.dropdown-toggle").first
        dropdown_locator = card.locator("ul.dropdown-menu.courses-dropdown").first

        # 1. Get the "Current" (Selected) Course
        # The button text is often truncated (e.g. "B.Tech. in Electrical Engineerin...")
        # The full text is usually in the first <li> of the dropdown that is NOT an input.
        # This <li> often has style="cursor: not-allowed;" because it's selected.
        current_course_name = ""
        try:
            # Strategy 1: Look for <li> with cursor: not-allowed (explicitly selected item)
            selected_li = dropdown_locator.locator("li[style*='cursor: not-allowed']").first
            if selected_li.count() > 0:
                current_course_name = selected_li.text_content().strip()
            
            # Strategy 2: If not found, look for <li> that is not input and has no data-search
            if not current_course_name:
                selected_li = dropdown_locator.locator("li").filter(has_not=dropdown_locator.locator("input")).filter(has_not=dropdown_locator.locator("[data-search]")).first
                if selected_li.count() > 0:
                    current_course_name = selected_li.text_content().strip()
            
            if current_course_name:
                current_course_name = re.sub(r'\s+', ' ', current_course_name)
        except Exception as e:
            logger.warning(f"  Failed to extract current course from hidden LI: {e}")

        # Fallback to button if we couldn't find it in the list
        if not current_course_name:
            if btn.count() > 0:
                current_course_name = btn.get_attribute("title") or btn.text_content()
                current_course_name = re.sub(r'\s+', ' ', current_course_name.strip()).strip()
        
        if current_course_name:
            try:
                current_details = self._extract_course_details_from_card(card)
                ordered_details = {"Course Name": current_course_name}
                ordered_details.update(current_details)
                courses.append(ordered_details)
            except Exception as e:
                logger.warning(f"  Failed to read details for current course: {e}")

        # 2. Iterate over the other courses in the dropdown
        def ensure_dropdown_visible() -> bool:
            for _ in range(3):
                if dropdown_locator.is_visible():
                    return True
                if btn.count() and btn.is_visible():
                    btn.click(timeout=2000)
                    page.wait_for_timeout(250)
            return dropdown_locator.is_visible()

        if ensure_dropdown_visible():
            items_count = dropdown_locator.locator("li[data-search]").count()
            logger.info(f"  Dropdown extraction: iterating {items_count} courses")

            for idx in range(items_count):
                success = False
                for attempt in range(2):
                    try:
                        if not ensure_dropdown_visible():
                            raise RuntimeError("Dropdown not visible")

                        item = dropdown_locator.locator("li[data-search]").nth(idx)
                        
                        # Strategy 1: Base64 decode 'data-of' attribute (Most reliable)
                        data_of = item.get_attribute("data-of")
                        course_name = ""
                        if data_of:
                            try:
                                course_name = base64.b64decode(data_of).decode('utf-8').strip()
                            except Exception:
                                pass
                        
                        # Strategy 2: Title attribute
                        if not course_name:
                            course_name = item.get_attribute("title")
                        
                        # Strategy 3: Text content
                        if not course_name:
                            course_name = item.text_content(timeout=2000)

                        course_name = re.sub(r'\s+', ' ', course_name.strip())
                        
                        item.click(timeout=2000)
                        # Wait for UI update (500ms is usually sufficient for AJAX)
                        page.wait_for_timeout(500)

                        details = self._extract_course_details_from_card(card)
                        ordered_details = {"Course Name": course_name}
                        ordered_details.update(details)
                        courses.append(ordered_details)
                        success = True
                        break
                    except Exception as e:
                        logger.debug(
                            f"  Dropdown extraction: attempt {attempt + 1} failed for course idx {idx}: {str(e)[:120]}"
                        )
                        try:
                            page.mouse.click(10, 10)
                            page.wait_for_timeout(100)
                        except Exception:
                            pass
                if not success:
                    logger.warning(f"  Dropdown extraction: skipping course idx {idx} after repeated failures")
        else:
            logger.warning("  Dropdown extraction: dropdown never became visible; relying on current course only")

        return courses

    def _capture_diagnostics(self, page: Page, label: str):
        """Persist screenshot + HTML to speed up debugging"""
        timestamp = int(time.time())
        safe_label = re.sub(r"[^A-Za-z0-9_-]", "_", label)
        screenshot_path = f"{safe_label}_{timestamp}.png"
        html_path = f"{safe_label}_{timestamp}.html"
        try:
            page.screenshot(path=screenshot_path, full_page=True)
            with open(html_path, "w", encoding="utf-8") as dump:
                dump.write(page.content())
            logger.info(f"Saved diagnostics to {screenshot_path} / {html_path}")
        except Exception as e:
            logger.error(f"[Diagnostics] Failed to capture page dump: {e}")

    def _validate_search_page(self, page: Page, context_label: str) -> bool:
        """Ensure we are still inside the college search experience"""
        current_url = page.url
        if current_url.startswith(COLLEGE_SEARCH_URL):
            return True

        logger.error(
            f"[Nav] Expected URL starting with {COLLEGE_SEARCH_URL}, but landed on {current_url}"
        )
        self._capture_diagnostics(page, context_label)
        return False

    def _scroll_to_load_all(self, page: Page):
        """Progressively scroll to load lazy-rendered college cards"""
        try:
            logger.info("Scrolling to load all colleges on current page...")
            last_height = page.evaluate("document.body.scrollHeight")
            no_change_count = 0

            for scroll in range(MAX_SCROLLS):
                page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(SCROLL_PAUSE_TIME)
                new_height = page.evaluate("document.body.scrollHeight")

                if new_height == last_height:
                    no_change_count += 1
                    if no_change_count >= 3:
                        logger.info("Reached end of dynamically loaded content")
                        break
                else:
                    no_change_count = 0
                    logger.info(f"Loaded more content (scroll {scroll + 1})")

                last_height = new_height

            page.evaluate("window.scrollTo(0, 0);")
            time.sleep(1)
        except Exception as e:
            logger.warning(f"[Scroll] Failed to scroll page: {e}")

    def _ensure_cards_visible(self, page: Page, page_number: int) -> bool:
        """Wait for college cards to appear"""
        try:
            logger.info("Waiting for college cards to render...")
            page.wait_for_selector("div.college-box", timeout=20000)
            return True
        except Exception:
            logger.warning("[Warn] Timeout waiting for college cards. Capturing diagnostics...")
            self._capture_diagnostics(page, f"debug_search_page_{page_number}")
            logger.info(f"Current URL: {page.url}")
            return False

    def _go_to_next_page(self, page: Page, current_page: int) -> bool:
        """Click the pagination next button if present"""
        selectors = [
            "a.next",
            "li.next a",
            "button.next",
            "a:has-text('Next')",
            "button:has-text('Next')",
        ]

        def _is_disabled(locator):
            try:
                classes = locator.get_attribute("class") or ""
                disabled_attr = locator.get_attribute("disabled")
                return bool(disabled_attr) or "disabled" in classes.lower()
            except Exception:
                return False

        for selector in selectors:
            locator = page.locator(selector)
            if locator.count() == 0:
                continue

            candidate = locator.first
            try:
                if not candidate.is_visible() or _is_disabled(candidate):
                    continue

                candidate.scroll_into_view_if_needed()
                candidate.click()
                logger.info(
                    f"Navigating to results page {current_page + 1} via selector '{selector}'"
                )
                try:
                    page.wait_for_load_state("domcontentloaded")
                    page.wait_for_load_state("networkidle", timeout=10000)
                except Exception:
                    pass
                return self._validate_search_page(page, f"pagination_page_{current_page + 1}")
            except Exception as e:
                logger.debug(f"Failed to use selector '{selector}' for pagination: {e}")

        logger.info("No further pagination controls detected; stopping.")
        return False

    def login(self, page: Page, context) -> (bool, Page):
        """Perform login using Playwright. Returns (success, page_to_use)"""
        logger.info(f"[Login] Navigating to MAIN_URL: {MAIN_URL}")
        page.goto(MAIN_URL, timeout=60000)
        page.wait_for_load_state("domcontentloaded")
        
        working_page = page
        
        # Click Student Dashboard
        try:
            dashboard_btn = page.get_by_text("Student Dashboard", exact=False).first
            if dashboard_btn.is_visible():
                logger.info("[Login] Clicking Student Dashboard...")

                # Check if it opens a new tab
                with context.expect_page() as new_page_info:
                    dashboard_btn.click()

                working_page = new_page_info.value
                working_page.wait_for_load_state("domcontentloaded")
                logger.info(f"[Login] Switched to new tab: {working_page.url}")
            else:
                logger.info("[Login] Student Dashboard button not found, trying direct link...")
                page.goto("https://careertest.edumilestones.com/student-dashboard/", timeout=60000)
                working_page = page
        except Exception as e:
             logger.error(f"[Login] Error interacting with dashboard button: {e}")
             logger.info("[Login] Trying direct navigation...")
             page.goto("https://careertest.edumilestones.com/student-dashboard/", timeout=60000)
             working_page = page
        
        logger.info(f"[Login] Working URL: {working_page.url}")
        
        # Check if already logged in
        if working_page.get_by_text("Logout", exact=False).is_visible() or working_page.get_by_text("Sign Out", exact=False).is_visible():
             logger.info("[Login] Already logged in!")
             return True, working_page

        # Handle Iframe
        try:
            logger.info("[Login] Waiting for login iframe...")
            try:
                frame_element = working_page.wait_for_selector("iframe.loginIframe", timeout=10000)
            except:
                logger.warning("[Login] Iframe not found. Dumping page...")
                working_page.screenshot(path="debug_dashboard.png")
                with open("debug_dashboard.html", "w", encoding="utf-8") as f:
                    f.write(working_page.content())
                raise Exception("Iframe not found")

            frame = frame_element.content_frame()
            
            # Click Login Tab
            logger.info("[Login] Switching to Login tab...")
            login_tab = frame.locator("a[href='#login']")
            if login_tab.is_visible():
                login_tab.click()
            else:
                working_page.evaluate("document.querySelector('#signup')?.classList.remove('in', 'active')")
                working_page.evaluate("document.querySelector('#login')?.classList.add('in', 'active')")
            
            # Fill credentials
            logger.info("[Login] Entering credentials...")
            frame.fill("#email", LOGIN_EMAIL)
            frame.fill("#password", LOGIN_PASSWORD)
            
            # Click Login
            logger.info("[Login] Clicking LOG IN...")
            frame.click("button:has-text('LOG IN')")
            
            # Wait for navigation
            logger.info("[Login] Waiting for dashboard redirection...")
            working_page.wait_for_url("**/student-dashboard**", timeout=30000)
            
            # Verify we are logged in
            if "student-dashboard" in working_page.url:
                 logger.info("[Login] Success!")
                 return True, working_page
            
            return False, working_page
            
        except Exception as e:
            logger.error(f"[Login] Error: {e}")
            return False, working_page

    def start(self, headless: bool = HEADLESS):
        """Initialize a persistent Playwright browser session."""
        if self.playwright:
            return
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(headless=headless)
        self.context = self.browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36'
        )
        self.page = self.context.new_page()
        success, self.page = self.login(self.page, self.context)
        if not success:
            self.stop()
            raise RuntimeError("Playwright login failed; unable to start session")
        time.sleep(2)

    def stop(self):
        """Cleanly tear down any active Playwright session."""
        try:
            if self.context:
                self.context.close()
        finally:
            self.context = None
        try:
            if self.browser:
                self.browser.close()
        finally:
            self.browser = None
        if self.playwright:
            self.playwright.stop()
            self.playwright = None
        self.page = None

    def _build_search_url(self, course_category, specialization, city, university) -> str:
        base_url = "https://careertest.edumilestones.com/india-colleges/"
        url = f"{base_url}MTgyMA%3D%3D/"
        url += f"{course_category or 'null'}/"
        url += f"{specialization or 'null'}/"
        url += f"{city or 'null'}/"
        url += f"{university or 'null'}"
        return url

    def _perform_scrape(self,
                        page: Page,
                        course_category: Optional[str],
                        specialization: Optional[str],
                        city: Optional[str],
                        university: Optional[str],
                        output_dir: Optional[str],
                        base_filename: Optional[str],
                        formats: List[str],
                        processed_colleges: Optional[Dict[str, Set[str]]]
                        ) -> List[Dict]:
        url = self._build_search_url(course_category, specialization, city, university)
        logger.info(f"Navigating to: {url}")
        page.goto(url, timeout=60000)

        if not self._validate_search_page(page, "initial_search_page"):
            raise RuntimeError("Landed outside the college search flow after navigation")

        results: List[Dict] = []
        page_number = 1
        processed_cards = 0
        new_records = 0
        processed_map: Dict[str, Set[str]] = processed_colleges if processed_colleges is not None else {}
        formats_lower = [fmt.lower() for fmt in formats] if formats else ['csv']

        while page_number <= MAX_PAGES:
            if not self._ensure_cards_visible(page, page_number):
                break

            self._scroll_to_load_all(page)

            card_locator = page.locator("div.college-box")
            card_count = card_locator.count()
            logger.info(f"Found {card_count} college cards on page {page_number}.")

            if card_count == 0:
                break

            for local_index in range(card_count):
                card = card_locator.nth(local_index)
                card_idx = processed_cards + local_index
                try:
                    logger.info(
                        f"Processing card {card_idx} (page {page_number}, index {local_index})..."
                    )

                    name = card.locator("h2").first.inner_text().strip()
                    logger.info(f"  Name: {name}")

                    name_lower = name.strip().lower()
                    already_complete = bool(processed_map) and all(
                        name_lower in processed_map.get(fmt, set())
                        for fmt in formats_lower
                    )
                    if already_complete:
                        logger.info(f"  [Skip] College '{name}' already processed for all requested formats.")
                        continue

                    location = card.locator("h4.location").first.inner_text().strip()
                    college_id = card.get_attribute("data-id") or ""
                    has_website = "Yes" if card.locator("a.get-university-website").count() > 0 else "No"

                    college_data = {
                        "College Name": name,
                        "Location": location,
                        "Course Category": "",
                        "Total Courses": "",
                        "College Type": "",
                        "Match Percentage": "",
                        "Match Level": "",
                        "Has Website Link": has_website,
                        "College ID": college_id,
                        "Courses": []
                    }

                    if card.locator("div.scholarship-div span").count() > 0:
                        college_data["Course Category"] = (
                            card.locator("div.scholarship-div span").first.inner_text().strip()
                        )

                    if card.locator("p.courses-trending").count() > 0:
                        courses_text = card.locator("p.courses-trending").first.inner_text()
                        match = re.search(r'(\d+)\s+Course', courses_text)
                        college_data["Total Courses"] = match.group(1) if match else ""

                    # Extract College Type (Private/Government/etc)
                    # Strategy A: Look for fa-graduation-cap icon
                    try:
                        grad_icon = card.locator(".college-basic-details i.fa-graduation-cap").first
                        if grad_icon.count() > 0:
                            college_data["College Type"] = grad_icon.locator("xpath=..").text_content().strip()
                    except Exception as e:
                        logger.warning(f"  Failed to extract college type via icon: {e}")

                    # Strategy B: Fallback to text search in LIs
                    if not college_data["College Type"]:
                        type_elems = card.locator("li").all()
                        for elem in type_elems:
                            text = elem.inner_text().strip()
                            if any(k in text.lower() for k in ['deemed', 'private', 'government', 'public']):
                                college_data["College Type"] = text
                                break

                    try:
                        if card.locator("text.percentage").count() > 0:
                            college_data["Match Percentage"] = (
                                card.locator("text.percentage").first.text_content().strip()
                            )
                        if card.locator("div.predictor-box-and-logo h4").count() > 0:
                            college_data["Match Level"] = (
                                card.locator("div.predictor-box-and-logo h4").first.text_content().strip()
                            )
                    except Exception as e:
                        logger.warning(f"  Failed to extract match info: {e}")

                    dom_courses = self._extract_courses_via_dom(card, page)
                    if dom_courses:
                        college_data["Courses"] = dom_courses
                    else:
                        logger.warning("  Dropdown extraction returned 0 courses; leaving list empty for now")

                    missing_formats = [
                        fmt for fmt in formats_lower
                        if name_lower not in processed_map.get(fmt, set())
                    ]

                    is_new_record = len(missing_formats) == len(formats_lower)
                    if is_new_record:
                        results.append(college_data)
                        new_records += 1
                    logger.info(f"  Successfully processed card {card_idx}")

                    if output_dir and base_filename:
                        saved = False
                        if 'csv' in missing_formats:
                            filename = f"{base_filename}.csv"
                            if append_to_csv(college_data, output_dir, filename):
                                logger.info(f"  [Saved] Progressively saved card {card_idx} to CSV")
                                processed_map.setdefault('csv', set()).add(name_lower)
                                saved = True
                        if 'json' in missing_formats:
                            filename = f"{base_filename}.jsonl"
                            if append_to_jsonl(college_data, output_dir, filename):
                                logger.info(f"  [Saved] Progressively saved card {card_idx} to JSONL")
                                processed_map.setdefault('json', set()).add(name_lower)
                                saved = True

                except Exception as e:
                    logger.error(f"Error processing card {card_idx}: {e}")

            processed_cards += card_count

            if page_number >= MAX_PAGES:
                logger.info("Reached MAX_PAGES limit; stopping pagination.")
                break

            if not self._go_to_next_page(page, page_number):
                break

            page_number += 1

        self.last_new_records = new_records
        self.last_total_cards = processed_cards
        return results

    def scrape_with_session(self,
                            course_category: Optional[str] = None,
                            specialization: Optional[str] = None,
                            city: Optional[str] = None,
                            university: Optional[str] = None,
                            output_dir: Optional[str] = None,
                            base_filename: Optional[str] = None,
                            headless: bool = HEADLESS,
                            formats: Optional[List[str]] = None,
                            processed_colleges: Optional[Dict[str, Set[str]]] = None
                            ) -> List[Dict]:
        if formats is None:
            formats = ['csv']
        if not self.playwright:
            self.start(headless=headless)
        if not self.page:
            raise RuntimeError("Playwright session not initialized")
        return self._perform_scrape(
            self.page,
            course_category,
            specialization,
            city,
            university,
            output_dir,
            base_filename,
            formats,
            processed_colleges
        )

    def scrape(self, course_category: str = None, specialization: str = None,
               city: str = None, university: str = None, output_dir: str = None,
               base_filename: str = None, headless: bool = HEADLESS, formats: List[str] = None,
               processed_colleges: Optional[Dict[str, Set[str]]] = None) -> List[Dict]:
        """Backward-compatible single-run scraper."""
        if formats is None:
            formats = ['csv']
        logger.info("Starting Playwright Scraper (single run mode)")
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless)
            context = browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36'
            )
            page = context.new_page()
            success, page = self.login(page, context)
            if not success:
                logger.error("[Error] Login failed. Aborting.")
                browser.close()
                return []
            time.sleep(2)
            try:
                return self._perform_scrape(
                    page,
                    course_category,
                    specialization,
                    city,
                    university,
                    output_dir,
                    base_filename,
                    formats,
                    processed_colleges
                )
            finally:
                browser.close()

