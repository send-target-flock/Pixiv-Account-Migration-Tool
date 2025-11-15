#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pixiv Account Migration Tool

Features:
- Migrate follows and bookmarks from one account to another
- Smart deduplication (skip items already present in target account)
- Chronological order preservation (reverse migration to maintain timeline)
- Intelligent rate-limit handling with configurable retries (-1 for infinite)
- Comprehensive final report on success or failure
- No intermediate files: only final report is written to disk

Note: This script uses refresh tokens for authentication.
Ensure tokens are valid and have necessary permissions.
"""

import time
import sys
from datetime import datetime
from pixivpy3 import AppPixivAPI


class PixivAccountMigrator:
    """Handles authentication, data extraction, deduplication, and migration."""

    def __init__(self, config):
        """Initialize APIs and store runtime configuration."""
        self.config = config
        self.source_api = AppPixivAPI()
        self.target_api = AppPixivAPI()
        self.source_user_id = None
        self.target_user_id = None

    def complete_login(self, source_token, target_token):
        """Log in to both source and target accounts using refresh tokens.
        
        Returns:
            bool: True if both logins succeed, False otherwise.
        """
        print("Logging in to source account...")
        try:
            self.source_api.auth(refresh_token=source_token)
            self.source_user_id = self.source_api.user_id
            print("Source login successful. User ID: {}".format(self.source_user_id))
        except Exception as e:
            print("Source login failed: {}".format(e))
            return False

        print("Logging in to target account...")
        try:
            self.target_api.auth(refresh_token=target_token)
            self.target_user_id = self.target_api.user_id
            print("Target login successful. User ID: {}".format(self.target_user_id))
            return True
        except Exception as e:
            print("Target login failed: {}".format(e))
            return False

    def _fetch_paginated_data(self, api_method, initial_args, result_key):
        """Fetch all pages of a paginated API response.
        
        Args:
            api_method: Bound API method (e.g., self.source_api.user_following)
            initial_args: Dict of initial arguments for the first request
            result_key: Attribute name of the result list in the response object
        
        Returns:
            list: Concatenated items from all pages.
        """
        all_items = []
        next_qs = None
        page = 1
        while True:
            print("  Fetching page {}...".format(page))
            if next_qs:
                result = api_method(**next_qs)
            else:
                result = api_method(**initial_args)
            time.sleep(self.config["extract_delay"])
            items_on_page = getattr(result, result_key, [])
            if not items_on_page:
                break
            all_items.extend(items_on_page)
            if hasattr(result, "next_url") and result.next_url:
                next_qs = self.source_api.parse_qs(result.next_url)
                page += 1
            else:
                break
        return all_items

    def _fetch_existing_following_set(self, restrict="public"):
        """Retrieve existing follows from target account for deduplication.
        
        Args:
            restrict (str): 'public' or 'private'
        
        Returns:
            set: User IDs already followed by target account under given visibility.
        """
        print("Fetching target account's existing {} following for deduplication...".format(restrict))
        try:
            user_previews = self._fetch_paginated_data(
                api_method=self.target_api.user_following,
                initial_args={"user_id": self.target_user_id, "restrict": restrict},
                result_key="user_previews"
            )
            user_ids = {p.user.id for p in user_previews}
            print("Found {} existing {} follows.".format(len(user_ids), restrict))
            return user_ids
        except Exception as e:
            print("Failed to fetch target's {} following: {}".format(restrict, e))
            return set()

    def _fetch_existing_bookmarks_set(self, restrict="public"):
        """Retrieve existing bookmarks from target account for deduplication.
        
        Args:
            restrict (str): 'public' or 'private'
        
        Returns:
            set: Illustration IDs already bookmarked by target account under given visibility.
        """
        print("Fetching target account's existing {} bookmarks for deduplication...".format(restrict))
        try:
            illusts = self._fetch_paginated_data(
                api_method=self.target_api.user_bookmarks_illust,
                initial_args={"user_id": self.target_user_id, "restrict": restrict},
                result_key="illusts"
            )
            illust_ids = {i.id for i in illusts}
            print("Found {} existing {} bookmarks.".format(len(illust_ids), restrict))
            return illust_ids
        except Exception as e:
            print("Failed to fetch target's {} bookmarks: {}".format(restrict, e))
            return set()

    def extract_following_list(self, user_id, restrict="public"):
        """Extract following list (user previews) from source account.
        
        Args:
            user_id (int): Source user ID.
            restrict (str): Visibility filter ('public' or 'private').
        
        Returns:
            list[dict] or None: List of user info dicts, or None on failure.
                Each dict contains: user_id, name, account, restrict.
        """
        print("Extracting {} following list for user {}...".format(restrict, user_id))
        try:
            user_previews = self._fetch_paginated_data(
                api_method=self.source_api.user_following,
                initial_args={"user_id": user_id, "restrict": restrict},
                result_key="user_previews"
            )
            following_list = [{
                "user_id": p.user.id,
                "name": p.user.name,
                "account": p.user.account,
                "restrict": restrict
            } for p in user_previews]
            print("Extracted {} {} follows.".format(len(following_list), restrict))
            return following_list
        except Exception as e:
            print("Error extracting {} follows: {}".format(restrict, e))
            return None

    def extract_bookmarks(self, user_id, restrict="public"):
        """Extract bookmarked illustrations from source account.
        
        Args:
            user_id (int): Source user ID.
            restrict (str): Visibility filter ('public' or 'private').
        
        Returns:
            list[dict] or None: List of bookmark info dicts, or None on failure.
                Each dict contains: illust_id, title, author, restrict.
        """
        print("Extracting {} bookmarks for user {}...".format(restrict, user_id))
        try:
            illusts = self._fetch_paginated_data(
                api_method=self.source_api.user_bookmarks_illust,
                initial_args={"user_id": user_id, "restrict": restrict},
                result_key="illusts"
            )
            bookmarks = [{
                "illust_id": i.id,
                "title": i.title,
                "author": i.user.name,
                "restrict": restrict
            } for i in illusts]
            print("Extracted {} {} bookmarks.".format(len(bookmarks), restrict))
            return bookmarks
        except Exception as e:
            print("Error extracting {} bookmarks: {}".format(restrict, e))
            return None

    def _perform_action_with_retry(self, action_func, log_name, *args, **kwargs):
        """Execute an API action with configurable retry on rate limits.
        
        Handles rate-limit errors specifically; other errors fail immediately.
        Applies base migration delay after first attempt.
        
        Args:
            action_func: API method to call (e.g., self.target_api.user_follow_add)
            log_name (str): Human-readable description for logging
            *args, **kwargs: Passed to action_func
        
        Returns:
            str: 'success' or 'failed'
        """
        migrate_delay = self.config["migrate_delay"]
        max_retries = self.config["max_retries"]
        retry_wait = self.config["retry_wait"]
        attempt = 0

        while True:
            try:
                result = action_func(*args, **kwargs)

                # Check for API-level error
                if hasattr(result, "error") and result.error:
                    error_msg = result.error.get("user_message") or result.error.get("message", "Unknown error")
                    # Detect rate limit in English or Japanese
                    is_rate_limit = any(kw in error_msg for kw in ["Rate Limit", "rate limit", "レート制限"])

                    if is_rate_limit:
                        # Retry if allowed
                        if max_retries < 0 or attempt < max_retries:
                            next_attempt = attempt + 2
                            retry_info = "infinite" if max_retries < 0 else "{}/{}".format(next_attempt, max_retries + 1)
                            print("Rate limited on '{}'. Retrying in {} seconds... (attempt {})".format(
                                log_name, retry_wait, retry_info))
                            time.sleep(retry_wait)
                            attempt += 1
                            continue
                        else:
                            print("Action failed: '{}' after {} attempts: {}".format(
                                log_name, max_retries + 1, error_msg))
                            return "failed"
                    else:
                        # Non-rate-limit error: fail immediately
                        print("Action failed: '{}' → {}".format(log_name, error_msg))
                        return "failed"
                else:
                    return "success"

            except Exception as e:
                print("Exception during action '{}': {}".format(log_name, e))
                return "failed"

            finally:
                # Apply base migration delay only after the first attempt
                if attempt == 0:
                    time.sleep(migrate_delay)

    def migrate_following(self, following_list):
        """Migrate following list to target account with deduplication and order preservation.
        
        Skips users already followed (respecting visibility). Migrates oldest first
        to preserve chronological order in target account's following list.
        
        Args:
            following_list (list[dict]): List from extract_following_list()
        
        Returns:
            tuple: (success_count: int, failed_list: list[dict])
        """
        # Fetch target's existing follows for deduplication
        existing_public = self._fetch_existing_following_set("public")
        existing_private = self._fetch_existing_following_set("private")

        # Filter out already-followed users
        filtered_list = []
        for user in following_list:
            uid = user["user_id"]
            restrict = user["restrict"]
            if restrict == "public" and uid in existing_public:
                continue
            if restrict == "private" and uid in existing_private:
                continue
            filtered_list.append(user)

        total_original = len(following_list)
        to_migrate = len(filtered_list)
        skipped = total_original - to_migrate
        if skipped > 0:
            print("Skipped {} already-followed users (deduplication enabled).".format(skipped))

        print("Starting migration of {} follows (base delay: {} seconds)...".format(to_migrate, self.config["migrate_delay"]))
        if to_migrate == 0:
            print("No new follows to migrate.")
            return 0, []

        success_count = 0
        failed_list = []

        # Reverse order: source returns newest first → migrate oldest first
        # so target's following list maintains correct chronological order
        for i, user in enumerate(reversed(filtered_list), 1):
            log_name = "{} (@{}) [{}]".format(user["name"], user["account"], user["restrict"])
            print("[{}/{}] Processing: {}".format(i, to_migrate, log_name))

            status = self._perform_action_with_retry(
                self.target_api.user_follow_add,
                log_name,
                user_id=user["user_id"],
                restrict=user["restrict"]
            )

            if status == "success":
                print("Successfully followed: {}".format(user["name"]))
                success_count += 1
            else:
                failed_list.append(user)

        print("Follow migration completed: {}/{} succeeded.".format(success_count, to_migrate))
        return success_count, failed_list

    def migrate_bookmarks(self, bookmarks):
        """Migrate bookmarks to target account with deduplication and order preservation.
        
        Skips already-bookmarked works (respecting visibility). Migrates oldest first
        to preserve chronological order in target account's bookmark list.
        
        Args:
            bookmarks (list[dict]): List from extract_bookmarks()
        
        Returns:
            tuple: (success_count: int, failed_list: list[dict])
        """
        # Fetch target's existing bookmarks for deduplication
        existing_public = self._fetch_existing_bookmarks_set("public")
        existing_private = self._fetch_existing_bookmarks_set("private")

        # Filter out already-bookmarked works
        filtered_list = []
        for bm in bookmarks:
            iid = bm["illust_id"]
            restrict = bm["restrict"]
            if restrict == "public" and iid in existing_public:
                continue
            if restrict == "private" and iid in existing_private:
                continue
            filtered_list.append(bm)

        total_original = len(bookmarks)
        to_migrate = len(filtered_list)
        skipped = total_original - to_migrate
        if skipped > 0:
            print("Skipped {} already-bookmarked works (deduplication enabled).".format(skipped))

        print("Starting migration of {} bookmarks (base delay: {} seconds)...".format(to_migrate, self.config["migrate_delay"]))
        if to_migrate == 0:
            print("No new bookmarks to migrate.")
            return 0, []

        success_count = 0
        failed_list = []

        # Reverse order: source returns newest first → migrate oldest first
        for i, bookmark in enumerate(reversed(filtered_list), 1):
            log_name = "'{}' by {} [{}]".format(bookmark["title"], bookmark["author"], bookmark["restrict"])
            print("[{}/{}] Processing: {}".format(i, to_migrate, log_name))

            status = self._perform_action_with_retry(
                self.target_api.illust_bookmark_add,
                log_name,
                illust_id=bookmark["illust_id"],
                restrict=bookmark["restrict"]
            )

            if status == "success":
                print("Successfully bookmarked: '{}'".format(bookmark["title"]))
                success_count += 1
            else:
                failed_list.append(bookmark)

        print("Bookmark migration completed: {}/{} succeeded.".format(success_count, to_migrate))
        return success_count, failed_list

    def generate_report(self, results):
        """Generate a final migration report regardless of success or failure.
        
        Always writes a report file named migration_report_YYYYMMDD_HHMMSS.txt.
        Includes error reasons, partial results, and failure details.
        
        Args:
            results (dict): Collected migration outcomes and errors.
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = "migration_report_{}.txt".format(timestamp)

        try:
            with open(report_file, "w", encoding="utf-8") as f:
                f.write("Pixiv Account Migration Report\n")
                f.write("=" * 50 + "\n")
                f.write("Migration Time: {}\n\n".format(datetime.now().strftime("%Y-%m-%d %H:%M:%S")))

                # Handle early termination
                if "error" in results:
                    f.write("Termination Reason: {}\n".format(results["error"]))
                    print("Generated error report: {}".format(report_file))
                    return

                # Handle no tasks executed
                if not results:
                    f.write("No migration tasks were executed.\n")
                    print("Generated empty report: {}".format(report_file))
                    return

                # Follow migration section
                if "following" in results:
                    res = results["following"]
                    if res.get("failed_extraction"):
                        f.write("Follow Migration: Extraction failed\n")
                    else:
                        f.write("Follow Migration: {}/{} succeeded\n".format(res["success"], res["total"]))
                        if res["failed"]:
                            f.write("Failed follows:\n")
                            for user in res["failed"]:
                                f.write("  - {} (@{}) [{}]\n".format(user["name"], user["account"], user["restrict"]))
                    f.write("\n")

                # Bookmark migration section (by visibility)
                if "bookmarks" in results:
                    for restrict_type in ["public", "private"]:
                        if restrict_type in results["bookmarks"]:
                            res = results["bookmarks"][restrict_type]
                            if res.get("failed_extraction"):
                                f.write("{} Bookmarks Migration: Extraction failed\n".format(restrict_type.capitalize()))
                            else:
                                f.write("{} Bookmarks Migration: {}/{} succeeded\n".format(
                                    restrict_type.capitalize(), res["success"], res["total"]))
                                if res["failed"]:
                                    f.write("Failed {} bookmarks:\n".format(restrict_type))
                                    for bm in res["failed"]:
                                        f.write("  - '{}' by {}\n".format(bm["title"], bm["author"]))
                            f.write("\n")

            print("Migration report saved to: {}".format(report_file))

        except Exception as e:
            print("Failed to generate report: {}".format(e))


def get_user_config():
    """Interactively collect runtime configuration from user."""
    print("Migration Configuration")
    print("-" * 30)

    def get_float_input(prompt, default):
        while True:
            val = input("Please set {}, default {} second: ".format(prompt, default)).strip()
            if val == "":
                return float(default)
            try:
                return float(val)
            except ValueError:
                print("  Invalid input. Please enter a number.")

    def get_int_input(prompt, default, allow_negative=False):
        hint = " (-1 for infinite retries)" if allow_negative else ""
        while True:
            val = input("Please set {}, default {}{}: ".format(prompt, default, hint)).strip()
            if val == "":
                return int(default)
            try:
                num = int(val)
                if allow_negative or num >= 0:
                    return num
                print("  Invalid input. Please enter a non-negative integer or -1.")
            except ValueError:
                suffix = " or -1" if allow_negative else ""
                print("  Invalid input. Please enter an integer{}.".format(suffix))

    config = {
        "extract_delay": get_float_input("delay between data extraction requests", 1.0),
        "migrate_delay": get_float_input("base delay between migration actions", 2.5),
        "max_retries": get_int_input("maximum retries on rate limit", 4, allow_negative=True),
        "retry_wait": get_int_input("wait time before retry", 90, allow_negative=False)
    }

    print("\nConfiguration confirmed:")
    print("  extract_delay: {} seconds".format(config["extract_delay"]))
    print("  migrate_delay: {} seconds".format(config["migrate_delay"]))
    retries_info = "infinite" if config["max_retries"] < 0 else str(config["max_retries"])
    print("  max_retries: {}".format(retries_info))
    print("  retry_wait: {} seconds".format(config["retry_wait"]))
    print()
    return config


def main():
    """Main entry point with error-safe report generation."""
    print("Pixiv Account Data Migration Tool (v5.3 - Clean, Report-Only, Error-Safe)")
    print("=" * 70)

    config = get_user_config()
    migrator = PixivAccountMigrator(config)

    print("Enter account credentials:")
    source_token = input("Source account refresh_token: ").strip()
    target_token = input("Target account refresh_token: ").strip()

    # Initialize results dict for final reporting
    results = {}

    try:
        # Attempt login
        if not migrator.complete_login(source_token, target_token):
            results["error"] = "Login failed"
            return

        # User selection
        print("\nSelect data to migrate:")
        migrate_pub_follow = input("Migrate public follows? (y/n): ").lower() == "y"
        migrate_priv_follow = input("Migrate private follows? (y/n): ").lower() == "y"
        migrate_pub_bookmark = input("Migrate public bookmarks? (y/n): ").lower() == "y"
        migrate_priv_bookmark = input("Migrate private bookmarks? (y/n): ").lower() == "y"

        if not any([migrate_pub_follow, migrate_priv_follow, migrate_pub_bookmark, migrate_priv_bookmark]):
            results["error"] = "No migration tasks selected"
            return

        # Process follows
        if migrate_pub_follow or migrate_priv_follow:
            print("\n" + "=" * 50)
            full_following = []
            extraction_ok = True
            if migrate_pub_follow:
                pub = migrator.extract_following_list(migrator.source_user_id, "public")
                if pub is None:
                    extraction_ok = False
                else:
                    full_following.extend(pub)
            if migrate_priv_follow:
                priv = migrator.extract_following_list(migrator.source_user_id, "private")
                if priv is None:
                    extraction_ok = False
                else:
                    full_following.extend(priv)

            if not extraction_ok:
                results["following"] = {"failed_extraction": True}
            elif full_following:
                success, failed = migrator.migrate_following(full_following)
                results["following"] = {
                    "success": success,
                    "total": len(full_following),
                    "failed": failed
                }

        # Process bookmarks
        if migrate_pub_bookmark or migrate_priv_bookmark:
            results["bookmarks"] = {}
            for restrict_type, should_migrate in [("public", migrate_pub_bookmark), ("private", migrate_priv_bookmark)]:
                if should_migrate:
                    print("\n" + "=" * 50)
                    bookmarks = migrator.extract_bookmarks(migrator.source_user_id, restrict_type)
                    if bookmarks is None:
                        results["bookmarks"][restrict_type] = {"failed_extraction": True}
                    else:
                        success, failed = migrator.migrate_bookmarks(bookmarks)
                        results["bookmarks"][restrict_type] = {
                            "success": success,
                            "total": len(bookmarks),
                            "failed": failed
                        }

    except KeyboardInterrupt:
        print("\nOperation interrupted by user.")
        results["error"] = "Interrupted by user"
    except Exception as e:
        print("Unexpected error: {}".format(e))
        results["error"] = "Unexpected error: {}".format(str(e))
    finally:
        print("\n" + "=" * 50)
        print("Generating final report...")
        migrator.generate_report(results)
        print("Report generation completed.")


if __name__ == "__main__":
    main()
