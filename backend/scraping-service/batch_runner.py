"""
Batch Runner for College Data Scraper
======================================

Executes multiple scraping tasks sequentially based on batch_config.py
"""

import sys
import os
import time
import csv
from datetime import datetime
from src.config import (
    LOGIN_EMAIL, 
    LOGIN_PASSWORD, 
    MAIN_URL, 
    COLLEGE_SEARCH_URL,
    HEADLESS,
    OUTPUT_DIR,
    SERVERLESS_MODE
)
from src.auth import create_driver, login, manual_login
from src.downloader import get_all_results, try_download_report, build_search_url
from src.utils import save_data, load_existing_colleges
from src.playwright_scraper import PlaywrightScraper
from batch_config import BATCH_TASKS, BATCH_DELAY, USE_CSV_CONFIG, CSV_CONFIG_FILE
from src.logger import setup_logger

logger = setup_logger()


class BatchRunner:
    """Handles batch execution of scraping tasks"""
    
    def __init__(self, headless=False, manual_login_mode=False, engine='selenium'):
        self.headless = headless
        self.manual_login_mode = manual_login_mode
        self.engine = engine
        self.driver = None
        self.logged_in = False
        self.results_summary = []
        self.playwright_scraper = None
        
    def load_tasks_from_csv(self, csv_file):
        """Load batch tasks from CSV file"""
        tasks = []
        try:
            with open(csv_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    task = {
                        'course_category': None if row.get('course_category', '').lower() in ['null', ''] else row['course_category'],
                        'specialization': None if row.get('specialization', '').lower() in ['null', ''] else row.get('specialization'),
                        'city': None if row.get('city', '').lower() in ['null', ''] else row.get('city'),
                        'university': None if row.get('university', '').lower() in ['null', ''] else row.get('university'),
                        'format': row.get('format', 'json')
                    }
                    tasks.append(task)
            logger.info(f"✅ Loaded {len(tasks)} tasks from {csv_file}")
        except FileNotFoundError:
            logger.error(f"❌ CSV file not found: {csv_file}")
            logger.info(f"   Please create the file or set USE_CSV_CONFIG=False in batch_config.py")
            sys.exit(1)
        except Exception as e:
            logger.error(f"❌ Error reading CSV file: {e}")
            sys.exit(1)
        
        return tasks
    
    def initialize_driver(self):
        """Initialize browser driver and perform login once"""
        logger.info("\n" + "="*70)
        logger.info("Initializing Browser and Login")
        logger.info("="*70)
        
        try:
            # Create browser driver
            logger.info("Creating browser instance...")
            headless_mode = HEADLESS or self.headless
            self.driver = create_driver(headless=headless_mode)
            
            # Login once
            if self.manual_login_mode:
                logger.info("\nOpening login page for manual login...")
                manual_login(self.driver, MAIN_URL)
                self.logged_in = True
            else:
                logger.info("\nAttempting automatic login...")
                login_success = login(self.driver, LOGIN_EMAIL, LOGIN_PASSWORD, MAIN_URL)
                
                if not login_success:
                    logger.warning("\n⚠️  Automatic login failed. Falling back to manual login...")
                    manual_login(self.driver, MAIN_URL)
                    self.logged_in = True
                else:
                    self.logged_in = True
            
            # Clean up extra tabs
            time.sleep(1)
            if len(self.driver.window_handles) > 1:
                logger.info("\nCleaning up extra tabs...")
                current_handle = self.driver.current_window_handle
                for handle in self.driver.window_handles:
                    if handle != current_handle:
                        try:
                            self.driver.switch_to.window(handle)
                            self.driver.close()
                        except:
                            pass
                self.driver.switch_to.window(current_handle)
                time.sleep(2)
            
            logger.info("✅ Browser initialized and logged in successfully!")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize browser: {e}")
            return False
    
    def execute_task(self, task_num, task, total_tasks):
        """Execute a single scraping task"""
        logger.info("\n" + "="*70)
        logger.info(f"Task {task_num}/{total_tasks}")
        logger.info("="*70)
        
        # Extract task parameters
        course_category = task.get('course_category')
        specialization = task.get('specialization')
        city = task.get('city')
        university = task.get('university')
        output_format = task.get('format', 'json')
        
        # Determine output formats
        output_formats = []
        if output_format == 'both':
            output_formats = ['csv', 'json']
        else:
            output_formats = [output_format]
        
        logger.info(f"Filters:")
        logger.info(f"  - Course Category: {course_category or 'All'}")
        logger.info(f"  - Specialization:  {specialization or 'All'}")
        logger.info(f"  - City:            {city or 'All'}")
        logger.info(f"  - University:      {university or 'All'}")
        logger.info(f"  - Output Format:   {', '.join(output_formats).upper()}")
        
        task_start_time = time.time()
        task_result = {
            'task_num': task_num,
            'course_category': course_category or 'All',
            'specialization': specialization or 'All',
            'city': city or 'All',
            'university': university or 'All',
            'format': ', '.join(output_formats).upper(),
            'status': 'Failed',
            'colleges_found': 0,
            'courses_found': 0,
            'files_saved': [],
            'duration': 0,
            'error': None,
            'note': None
        }
        
        try:
            if self.engine == 'playwright':
                self._run_playwright_task(
                    task_result,
                    output_formats,
                    course_category,
                    specialization,
                    city,
                    university
                )
            else:
                self._run_selenium_task(
                    task_result,
                    output_formats,
                    course_category,
                    specialization,
                    city,
                    university,
                    task_num
                )
        except Exception as e:
            logger.error(f"\n❌ Task {task_num} failed: {e}")
            task_result['error'] = str(e)
            import traceback
            traceback.print_exc()
        
        task_result['duration'] = time.time() - task_start_time
        self.results_summary.append(task_result)
        
        return task_result['status'] == 'Success'

    def _build_base_filename(self, course_category, specialization, city, university):
        filter_parts = []
        if course_category:
            filter_parts.append(course_category)
        if specialization:
            filter_parts.append(specialization)
        if city:
            filter_parts.append(city)
        if university:
            filter_parts.append(university)
        base_filename = "_".join(filter_parts) if filter_parts else "colleges_data"
        base_filename = base_filename.replace(" ", "_")
        return base_filename

    def _run_playwright_task(self, task_result, output_formats, course_category, specialization, city, university):
        headless_mode = HEADLESS or self.headless
        if self.playwright_scraper is None:
            self.playwright_scraper = PlaywrightScraper()
            self.playwright_scraper.start(headless=headless_mode)

        logger.info("\nRunning task via Playwright engine...")
        base_filename = self._build_base_filename(course_category, specialization, city, university)
        processed_colleges = load_existing_colleges(OUTPUT_DIR, base_filename, output_formats)
        existing_total = 0
        if processed_colleges:
            combined = set()
            for names in processed_colleges.values():
                combined.update(names)
            existing_total = len(combined)
        if existing_total:
            logger.info(f"Resumability: skipping {existing_total} already-processed colleges if encountered.")

        try:
            colleges = self.playwright_scraper.scrape_with_session(
                course_category,
                specialization,
                city,
                university,
                output_dir=OUTPUT_DIR,
                base_filename=base_filename,
                headless=headless_mode,
                formats=output_formats,
                processed_colleges=processed_colleges
            )
        except Exception as e:
            logger.warning(f"Playwright session encountered an error ({e}); restarting once...")
            self.playwright_scraper.stop()
            self.playwright_scraper.start(headless=headless_mode)
            colleges = self.playwright_scraper.scrape_with_session(
                course_category,
                specialization,
                city,
                university,
                output_dir=OUTPUT_DIR,
                base_filename=base_filename,
                headless=headless_mode,
                formats=output_formats,
                processed_colleges=processed_colleges
            )
        total_cards_seen = getattr(self.playwright_scraper, 'last_total_cards', 0)
        new_records = getattr(self.playwright_scraper, 'last_new_records', len(colleges))

        if not colleges:
            if total_cards_seen > 0:
                task_result['status'] = 'Success (No Updates)'
                task_result['note'] = "No new colleges detected; existing export already up to date."
                task_result['error'] = None
                logger.info("\nℹ️  No new colleges detected; existing data already up to date.")
            else:
                task_result['error'] = "No colleges found for given filters"
                logger.warning("\n⚠️  Warning: No college data extracted")
            return
        total_courses = sum(len(c.get('Courses', [])) for c in colleges)
        saved_files = save_data(colleges, OUTPUT_DIR, base_filename, output_formats)
        task_result['status'] = 'Success'
        task_result['colleges_found'] = len(colleges)
        task_result['courses_found'] = total_courses
        task_result['files_saved'] = list(saved_files.values())
        task_result['note'] = None
        logger.info(f"\n✅ Playwright task completed! Colleges: {len(colleges)}, Courses: {total_courses}")
        for fmt, filepath in saved_files.items():
            logger.info(f"   {fmt.upper()}: {filepath}")

    def _run_selenium_task(self, task_result, output_formats, course_category, specialization, city, university, task_num):
        # Build search URL with filters
        search_url = build_search_url(
            COLLEGE_SEARCH_URL,
            course_category,
            specialization,
            city,
            university
        )
        
        # Navigate to college search page with filters
        logger.info(f"\nNavigating to search page...")
        logger.info(f"URL: {search_url}")
        self.driver.get(search_url)
        
        # Wait for page to load
        time.sleep(5)
        
        # Try to download via Report button first (if available)
        logger.info(f"\nAttempting to download CSV via Report button...")
        report_downloaded = try_download_report(self.driver)
        
        # Extract all college data
        logger.info(f"\nExtracting college data from page...")
        colleges = get_all_results(self.driver)
        
        if not colleges and not report_downloaded:
            logger.warning("\n⚠️  Warning: No college data extracted")
            task_result['error'] = "No colleges found for given filters"
            return
        if colleges:
            total_courses = sum(len(c.get('Courses', [])) for c in colleges)
            base_filename = self._build_base_filename(course_category, specialization, city, university)
            logger.info(f"\nSaving {len(colleges)} colleges...")
            saved_files = save_data(colleges, OUTPUT_DIR, base_filename, output_formats)
            task_result['status'] = 'Success'
            task_result['colleges_found'] = len(colleges)
            task_result['courses_found'] = total_courses
            task_result['files_saved'] = list(saved_files.values())
            logger.info(f"\n✅ Task {task_num} completed successfully!")
            logger.info(f"   Colleges: {len(colleges)}")
            logger.info(f"   Courses: {total_courses}")
            for fmt, filepath in saved_files.items():
                logger.info(f"   {fmt.upper()}: {filepath}")
        if report_downloaded:
            logger.info("\n✅ CSV download initiated via Report button")
            if task_result['status'] != 'Success':
                task_result['status'] = 'Success (Report Download)'
    
    def print_summary(self):
        """Print summary of all executed tasks"""
        logger.info("\n" + "="*70)
        logger.info("BATCH EXECUTION SUMMARY")
        logger.info("="*70)
        
        total_tasks = len(self.results_summary)
        successful_tasks = sum(1 for r in self.results_summary if r['status'].lower().startswith('success'))
        failed_tasks = total_tasks - successful_tasks
        total_colleges = sum(r['colleges_found'] for r in self.results_summary)
        total_duration = sum(r['duration'] for r in self.results_summary)
        total_courses = sum(r['courses_found'] for r in self.results_summary)
        
        logger.info(f"\nOverall Statistics:")
        logger.info(f"  Total Tasks:        {total_tasks}")
        logger.info(f"  Successful:         {successful_tasks}")
        logger.info(f"  Failed:             {failed_tasks}")
        logger.info(f"  Total New Colleges: {total_colleges}")
        logger.info(f"  Total New Courses:  {total_courses}")
        logger.info(f"  Total Duration:     {total_duration:.2f}s ({total_duration/60:.2f} min)")
        
        logger.info(f"\nTask Details:")
        logger.info("-" * 70)
        
        for result in self.results_summary:
            status_icon = "✅" if result['status'] == 'Success' else "❌"
            logger.info(f"\n{status_icon} Task {result['task_num']}: {result['status']}")
            logger.info(f"   Category: {result['course_category']}, City: {result['city']}")
            logger.info(f"   New Colleges: {result['colleges_found']}, New Courses: {result['courses_found']}")
            logger.info(f"   Duration: {result['duration']:.2f}s")
            
            if result['files_saved']:
                for filepath in result['files_saved']:
                    logger.info(f"   Saved: {filepath}")
            
            if result['error']:
                logger.info(f"   Error: {result['error']}")
            elif result.get('note'):
                logger.info(f"   Note: {result['note']}")
        
        logger.info("\n" + "="*70)
        
        # Save summary to file
        self.save_summary_report()
    
    def save_summary_report(self):
        """Save execution summary to a file"""
        # Skip file writes in serverless mode (read-only file system)
        if SERVERLESS_MODE:
            logger.info("SERVERLESS_MODE: Skipping summary report file write")
            return
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_filename = f"batch_summary_{timestamp}.txt"
        report_path = os.path.join(OUTPUT_DIR, report_filename)
        
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write("="*70 + "\n")
            f.write("BATCH EXECUTION SUMMARY\n")
            f.write("="*70 + "\n")
            f.write(f"Execution Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            
            total_tasks = len(self.results_summary)
            successful_tasks = sum(1 for r in self.results_summary if r['status'].lower().startswith('success'))
            failed_tasks = total_tasks - successful_tasks
            total_colleges = sum(r['colleges_found'] for r in self.results_summary)
            total_courses = sum(r['courses_found'] for r in self.results_summary)
            total_duration = sum(r['duration'] for r in self.results_summary)
            
            f.write("Overall Statistics:\n")
            f.write(f"  Total Tasks:        {total_tasks}\n")
            f.write(f"  Successful:         {successful_tasks}\n")
            f.write(f"  Failed:             {failed_tasks}\n")
            f.write(f"  Total New Colleges: {total_colleges}\n")
            f.write(f"  Total New Courses:  {total_courses}\n")
            f.write(f"  Total Duration:     {total_duration:.2f}s ({total_duration/60:.2f} min)\n\n")
            
            f.write("Task Details:\n")
            f.write("-" * 70 + "\n")
            
            for result in self.results_summary:
                f.write(f"\nTask {result['task_num']}: {result['status']}\n")
                f.write(f"  Filters:\n")
                f.write(f"    - Course Category: {result['course_category']}\n")
                f.write(f"    - Specialization:  {result['specialization']}\n")
                f.write(f"    - City:            {result['city']}\n")
                f.write(f"    - University:      {result['university']}\n")
                f.write(f"  Results:\n")
                f.write(f"    - New Colleges:    {result['colleges_found']}\n")
                f.write(f"    - New Courses:     {result['courses_found']}\n")
                f.write(f"    - Duration:        {result['duration']:.2f}s\n")
                f.write(f"    - Format:          {result['format']}\n")
                
                if result['files_saved']:
                    f.write(f"  Files Saved:\n")
                    for filepath in result['files_saved']:
                        f.write(f"    - {filepath}\n")
                
                if result['error']:
                    f.write(f"  Error: {result['error']}\n")
                elif result.get('note'):
                    f.write(f"  Note: {result['note']}\n")
        
        logger.info(f"\n📄 Summary report saved to: {report_path}")
    
    def run(self):
        """Run all batch tasks"""
        start_time = time.time()
        
        # Load tasks
        if USE_CSV_CONFIG:
            logger.info("Loading tasks from CSV file...")
            tasks = self.load_tasks_from_csv(CSV_CONFIG_FILE)
        else:
            logger.info("Loading tasks from batch_config.py...")
            tasks = BATCH_TASKS
        
        if not tasks:
            logger.warning("❌ No tasks defined. Please add tasks to batch_config.py or CSV file.")
            return
        
        logger.info(f"✅ Loaded {len(tasks)} tasks to execute")
        
        # Initialize driver/session depending on engine
        if self.engine == 'selenium':
            if not self.initialize_driver():
                logger.error("❌ Failed to initialize browser. Aborting batch execution.")
                return
        else:
            if self.manual_login_mode:
                logger.warning("Manual login flag is ignored when using the Playwright engine.")
            if self.playwright_scraper is None:
                self.playwright_scraper = PlaywrightScraper()
            try:
                self.playwright_scraper.start(headless=HEADLESS or self.headless)
                logger.info("✅ Playwright session initialized successfully!")
            except Exception as e:
                logger.error(f"❌ Failed to initialize Playwright session: {e}")
                return
        
        # Execute all tasks
        try:
            for idx, task in enumerate(tasks, 1):
                self.execute_task(idx, task, len(tasks))
                
                # Add delay between tasks (except after the last one)
                if idx < len(tasks):
                    logger.info(f"\n⏳ Waiting {BATCH_DELAY} seconds before next task...")
                    time.sleep(BATCH_DELAY)
            
        except KeyboardInterrupt:
            logger.warning("\n\n⚠️  Batch execution interrupted by user")
        except Exception as e:
            logger.error(f"\n❌ Batch execution error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            # Print summary
            self.print_summary()
            
            # Close browsers
            if self.driver:
                logger.info("\nClosing browser...")
                self.driver.quit()
            if self.playwright_scraper:
                logger.info("\nClosing Playwright session...")
                self.playwright_scraper.stop()
            
            total_time = time.time() - start_time
            logger.info(f"\n⏱️  Total execution time: {total_time:.2f}s ({total_time/60:.2f} min)")
            logger.info("Done!")


def main():
    """Main entry point for batch runner"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Batch College Data Scraper - Execute multiple scraping tasks',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument('--headless', 
                        action='store_true',
                        help='Run browser in headless mode')
    parser.add_argument('--manual-login',
                        action='store_true',
                        help='Use manual login instead of automatic (Selenium only)')
    parser.add_argument('--engine',
                        choices=['selenium', 'playwright'],
                        default='selenium',
                        help='Scraping engine to use for all tasks (default: selenium)')
    
    args = parser.parse_args()
    
    logger.info("="*70)
    logger.info("College Data Scraper - Batch Mode")
    logger.info("="*70)
    logger.info("\n")
    
    runner = BatchRunner(
        headless=args.headless,
        manual_login_mode=args.manual_login,
        engine=args.engine
    )
    
    runner.run()


if __name__ == "__main__":
    main()