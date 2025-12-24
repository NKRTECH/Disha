"""
Main script to login, filter, and download college data
Usage:
    python main.py <course_category> <specialization> <city> <university> [--format csv|json|both]
    
Example:
    python main.py Engineering Science Chandigarh Chitkara --format both
    python main.py Engineering null Delhi null --format json
"""

import sys
import os
import argparse
import re
from src.config import (
    LOGIN_EMAIL, 
    LOGIN_PASSWORD, 
    MAIN_URL, 
    COLLEGE_SEARCH_URL,
    HEADLESS,
    OUTPUT_DIR,
    CSV_FILENAME
)
from src.auth import create_driver, login, manual_login
from src.downloader import get_all_results, try_download_report, build_search_url
from src.utils import save_data, load_existing_colleges
from src.playwright_scraper import PlaywrightScraper
from src.logger import setup_logger

logger = setup_logger()


def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description='College Data Downloader - Scrape college information with filters',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py Engineering Science Chandigarh Chitkara
  python main.py Engineering null Delhi null --format both
  python main.py null null Bangalore null --format json
  
Note: Use 'null' for filters you want to skip
        """
    )
    
    parser.add_argument('course_category', 
                        help='Course category (e.g., Engineering, Management) or null')
    parser.add_argument('specialization', 
                        help='Specialization (e.g., Science, Computer) or null')
    parser.add_argument('city', 
                        help='City name (e.g., Delhi, Bangalore) or null')
    parser.add_argument('university', 
                        help='University name (e.g., Chitkara, VIT) or null')
    parser.add_argument('--format', '-f', 
                        choices=['csv', 'json', 'both'],
                        default='csv',
                        help='Output format (default: csv)')
    parser.add_argument('--headless', 
                        action='store_true',
                        help='Run browser in headless mode')
    parser.add_argument('--manual-login',
                        action='store_true',
                        help='Use manual login instead of automatic (Selenium only)')
    parser.add_argument('--save',
                        action='store_true',
                        help='Save scraped data to Supabase')
    parser.add_argument('--engine',
                        choices=['selenium', 'playwright'],
                        default='selenium',
                        help='Scraping engine to use (default: selenium)')
    parser.add_argument('--output', '-o',
                        help='Override base filename (without extension). Defaults to filters combination.')
    parser.add_argument('--job-id',
                        help='Supabase Job ID to update with save status')
    
    return parser.parse_args() 

def build_base_filename(course_category, specialization, city, university, override: str = None) -> str:
    """Determine a safe base filename for exports"""
    if override:
        candidate = override.strip()
    else:
        filter_parts = [part for part in (course_category, specialization, city, university) if part]
        candidate = "_".join(filter_parts) if filter_parts else "colleges_data"

    candidate = candidate.replace(" ", "_")
    candidate = re.sub(r"[^A-Za-z0-9_.-]+", "_", candidate)
    candidate = candidate.strip("._") or "colleges_data"
    return candidate


def main():
    """Main function to execute the data download process"""
    args = parse_arguments()

    # Convert 'null' strings to None
    course_category = None if args.course_category.lower() == 'null' else args.course_category
    specialization = None if args.specialization.lower() == 'null' else args.specialization
    city = None if args.city.lower() == 'null' else args.city
    university = None if args.university.lower() == 'null' else args.university
    
    # Determine output formats
    output_formats = []
    if args.format == 'both':
        output_formats = ['csv', 'json']
    else:
        output_formats = [args.format]
    
    logger.info("=" * 70)
    logger.info("College Data Downloader")
    logger.info("=" * 70)
    logger.info(f"Filters:")
    logger.info(f"  - Course Category: {course_category or 'All'}")
    logger.info(f"  - Specialization:  {specialization or 'All'}")
    logger.info(f"  - City:            {city or 'All'}")
    logger.info(f"  - University:      {university or 'All'}")
    logger.info(f"  - Output Format:   {', '.join(output_formats).upper()}")
    logger.info(f"  - Engine:          {args.engine.upper()}")
    logger.info("")
    
    base_filename = build_base_filename(course_category, specialization, city, university, args.output)

    if args.engine == 'playwright':
        try:
            scraper = PlaywrightScraper()
            # Load existing data for resumability
            processed_colleges = load_existing_colleges(OUTPUT_DIR, base_filename, output_formats)
            if processed_colleges:
                combined = set()
                for names in processed_colleges.values():
                    combined.update(names)
                if combined:
                    logger.info(f"Resuming scrape. Found {len(combined)} already processed colleges across requested formats.")

            # Pass output_dir and base_filename for progressive saving
            colleges = scraper.scrape(
                course_category, 
                specialization, 
                city, 
                university,
                output_dir=OUTPUT_DIR,
                base_filename=base_filename,
                headless=args.headless,
                formats=output_formats,
                processed_colleges=processed_colleges
            )
            
            if colleges:
                logger.info(f"\nStep 5: Finalizing and deduplicating {len(colleges)} colleges...")
                saved_files = save_data(
                    colleges, 
                    OUTPUT_DIR, 
                    base_filename, 
                    output_formats,
                    push_to_supabase=args.save,
                    career_path=course_category,
                    specialization=specialization,
                    location=city,
                    university=university,
                    job_id=args.job_id
                )
                
                logger.info(f"\n[OK] Success!")
                logger.info(f"Summary:")
                logger.info(f"  - Total colleges found: {len(colleges)}")
                for fmt, filepath in saved_files.items():
                    logger.info(f"  - {fmt.upper()} file: {filepath}")
            else:
                logger.warning("\n[WARN]  No data found using Playwright engine.")
                
        except Exception as e:
            logger.error(f"\n[ERROR] Playwright Error: {e}")
            import traceback
            traceback.print_exc()
        return

    driver = None
    try:
        # Create browser driver
        logger.info("Initializing browser...")
        headless_mode = HEADLESS or args.headless
        driver = create_driver(headless=headless_mode)
        
        # Login
        import time
        if args.manual_login:
            logger.info("\nStep 1: Opening login page for manual login...")
            manual_login(driver, MAIN_URL)
        else:
            logger.info("\nStep 1: Attempting automatic login...")
            login_success = login(driver, LOGIN_EMAIL, LOGIN_PASSWORD, MAIN_URL)
            
            if not login_success:
                if headless_mode:
                    logger.error("\n[ERROR] Automatic login failed in headless mode. Cannot fall back to manual login.")
                else:
                    logger.warning("\n[WARN]  Automatic login failed. Falling back to manual login...")
                    manual_login(driver, MAIN_URL)
        
        # Clean up extra tabs
        time.sleep(1)
        if len(driver.window_handles) > 1:
            logger.info(f"\nCleaning up extra tabs...")
            current_handle = driver.current_window_handle
            for handle in driver.window_handles:
                if handle != current_handle:
                    try:
                        driver.switch_to.window(handle)
                        driver.close()
                    except:
                        pass
            driver.switch_to.window(current_handle)
            time.sleep(2)
        
        # Build search URL with filters
        search_url = build_search_url(
            COLLEGE_SEARCH_URL,
            course_category,
            specialization,
            city,
            university
        )
        
        # Navigate to college search page with filters
        logger.info(f"\nStep 2: Navigating to college search page with filters...")
        logger.info(f"URL: {search_url}")
        driver.get(search_url)
        
        # Wait for page to load
        time.sleep(5)
        
        # Try to download via Report button first (if available)
        logger.info(f"\nStep 3: Attempting to download CSV via Report button...")
        report_downloaded = try_download_report(driver)
        
        # Extract all college data
        logger.info(f"\nStep 4: Extracting college data from page...")
        colleges = get_all_results(driver)
        
        if not colleges and not report_downloaded:
            logger.warning("\n[WARN]  Warning: No college data extracted and Report button didn't work.")
            logger.info("Possible reasons:")
            logger.info("  - No colleges match the specified filters")
            logger.info("  - Page structure changed")
            logger.info("  - Login session expired")
            if not headless_mode:
                input("\nPress Enter to close the browser...")
        else:
            if colleges:
                # Save to specified format(s)
                logger.info(f"\nStep 5: Saving {len(colleges)} colleges...")
                saved_files = save_data(
                    colleges, 
                    OUTPUT_DIR, 
                    base_filename, 
                    output_formats,
                    push_to_supabase=args.save,
                    career_path=course_category,
                    specialization=specialization,
                    location=city,
                    university=university,
                    job_id=args.job_id
                )
                
                logger.info(f"\n[OK] Success!")
                logger.info(f"Summary:")
                logger.info(f"  - Total colleges found: {len(colleges)}")
                for fmt, filepath in saved_files.items():
                    logger.info(f"  - {fmt.upper()} file: {filepath}")
            
            if report_downloaded:
                logger.info("\n[OK] CSV download initiated via Report button")
                logger.info("  - Check your browser's default download folder")
        
        if not headless_mode:
            input("\nPress Enter to close the browser...")
            
    except KeyboardInterrupt:
        logger.warning("\n\n[WARN]  Process interrupted by user")
    except Exception as e:
        logger.error(f"\n[ERROR] Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if driver:
            logger.info("\nClosing browser...")
            driver.quit()
            logger.info("Done!")


if __name__ == "__main__":
    main()