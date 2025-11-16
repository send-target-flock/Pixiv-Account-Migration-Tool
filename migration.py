#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
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
        self.target_follows_existing = {"public": set(), "private": set()}
        self.target_bookmarks_existing = {"public": set(), "private": set()}

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
        """Retrieve existing follows from target account.
        
        Args:
            restrict (str): 'public' or 'private'
        
        Returns:
            set: User IDs already followed by target account under given visibility.
        """
        try:
            user_previews = self._fetch_paginated_data(
                api_method=self.target_api.user_following,
                initial_args={"user_id": self.target_user_id, "restrict": restrict},
                result_key="user_previews"
            )
            return {p.user.id for p in user_previews}
        except Exception as e:
            print("Failed to fetch target's {} following: {}".format(restrict, e))
            return set()

    def _fetch_existing_bookmarks_set(self, restrict="public"):
        """Retrieve existing bookmarks from target account.
        
        Args:
            restrict (str): 'public' or 'private'
        
        Returns:
            set: Illustration IDs already bookmarked by target account under given visibility.
        """
        try:
            illusts = self._fetch_paginated_data(
                api_method=self.target_api.user_bookmarks_illust,
                initial_args={"user_id": self.target_user_id, "restrict": restrict},
                result_key="illusts"
            )
            return {i.id for i in illusts}
        except Exception as e:
            print("Failed to fetch target's {} bookmarks: {}".format(restrict, e))
            return set()

    def prepare_dedup_data(self, need_follows=False, need_bookmarks=False):
        """Pre-fetch target account's existing data for deduplication."""
        if not need_follows and not need_bookmarks:
            return

        print("→ Preparing deduplication data...")
        print("-" * 40)

        if need_follows:
            print("→ Fetching target's existing follows...")
            self.target_follows_existing["public"] = self._fetch_existing_following_set("public")
            count_pub = len(self.target_follows_existing["public"])
            self.target_follows_existing["private"] = self._fetch_existing_following_set("private")
            count_priv = len(self.target_follows_existing["private"])
            print("  ✓ Found {} public, {} private follows.".format(count_pub, count_priv))

        if need_bookmarks:
            print("→ Fetching target's existing bookmarks...")
            self.target_bookmarks_existing["public"] = self._fetch_existing_bookmarks_set("public")
            count_pub = len(self.target_bookmarks_existing["public"])
            self.target_bookmarks_existing["private"] = self._fetch_existing_bookmarks_set("private")
            count_priv = len(self.target_bookmarks_existing["private"])
            print("  ✓ Found {} public, {} private bookmarks.".format(count_pub, count_priv))

        print()

    def extract_following_list(self, user_id, restrict="public"):
        """Extract following list from source account.
        
        Returns:
            list[dict] or None: Each dict: user_id, name, account, restrict.
        """
        print("→ Extracting source {} follows...".format(restrict))
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
            print("  Extracted {} {} follows.".format(len(following_list), restrict))
            return following_list
        except Exception as e:
            print("  Error extracting {} follows: {}".format(restrict, e))
            return None

    def extract_bookmarks(self, user_id, restrict="public"):
        """Extract bookmarked illustrations from source account.
        
        Returns:
            list[dict] or None: Each dict: illust_id, title, author, restrict.
        """
        print("→ Extracting source {} bookmarks...".format(restrict))
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
            print("  Extracted {} {} bookmarks.".format(len(bookmarks), restrict))
            return bookmarks
        except Exception as e:
            print("  Error extracting {} bookmarks: {}".format(restrict, e))
            return None

    def _perform_action_with_retry(self, action_func, log_name, *args, **kwargs):
        """Execute an API action with configurable retry on rate limits."""
        migrate_delay = self.config["migrate_delay"]
        max_retries = self.config["max_retries"]
        retry_wait = self.config["retry_wait"]
        attempt = 0

        while True:
            try:
                result = action_func(*args, **kwargs)

                if hasattr(result, "error") and result.error:
                    error_msg = result.error.get("user_message") or result.error.get("message", "Unknown error")
                    is_rate_limit = any(kw in error_msg for kw in ["Rate Limit", "rate limit", "レート制限"])

                    if is_rate_limit:
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
                        print("Action failed: '{}' → {}".format(log_name, error_msg))
                        return "failed"
                else:
                    return "success"

            except Exception as e:
                print("Exception during action '{}': {}".format(log_name, e))
                return "failed"

            finally:
                if attempt == 0:
                    time.sleep(migrate_delay)

    def migrate_following(self, following_list):
        """Migrate following list with deduplication and order preservation."""
        existing_public = self.target_follows_existing["public"]
        existing_private = self.target_follows_existing["private"]

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
            print("Skipped {} already-followed users.".format(skipped))

        print("Starting migration of {} follows (base delay: {} seconds)...".format(to_migrate, self.config["migrate_delay"]))
        if to_migrate == 0:
            print("No new follows to migrate.")
            return 0, []

        success_count = 0
        failed_list = []

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
                print("  ✓ Successfully followed: {}".format(user["name"]))
                success_count += 1
            else:
                failed_list.append(user)

        print("Follow migration completed: {}/{} succeeded.".format(success_count, to_migrate))
        return success_count, failed_list

    def migrate_bookmarks(self, bookmarks):
        """Migrate bookmarks with deduplication and order preservation."""
        existing_public = self.target_bookmarks_existing["public"]
        existing_private = self.target_bookmarks_existing["private"]

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
            print("Skipped {} already-bookmarked works.".format(skipped))

        print("Starting migration of {} bookmarks (base delay: {} seconds)...".format(to_migrate, self.config["migrate_delay"]))
        if to_migrate == 0:
            print("No new bookmarks to migrate.")
            return 0, []

        success_count = 0
        failed_list = []

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
                print("  ✓ Successfully bookmarked: '{}'".format(bookmark["title"]))
                success_count += 1
            else:
                failed_list.append(bookmark)

        print("Bookmark migration completed: {}/{} succeeded.".format(success_count, to_migrate))
        return success_count, failed_list

    def generate_report(self, results):
        """Generate final migration report regardless of outcome."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = "migration_report_{}.txt".format(timestamp)

        try:
            with open(report_file, "w", encoding="utf-8") as f:
                f.write("Pixiv Account Migration Report\n")
                f.write("=" * 50 + "\n")
                f.write("Migration Time: {}\n\n".format(datetime.now().strftime("%Y-%m-%d %H:%M:%S")))

                if "error" in results:
                    f.write("Termination Reason: {}\n".format(results["error"]))
                    print("Generated error report: {}".format(report_file))
                    return

                if not results:
                    f.write("No migration tasks were executed.\n")
                    print("Generated empty report: {}".format(report_file))
                    return

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
    """Interactively collect runtime configuration."""
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
    """Main entry point with two-phase execution and error-safe reporting."""
    print("Pixiv Account Data Migration Tool (v5.4 - Two-Phase, Clean)")
    print("=" * 65)

    config = get_user_config()
    migrator = PixivAccountMigrator(config)

    print("Enter account credentials:")
    source_token = input("Source account refresh_token: ").strip()
    target_token = input("Target account refresh_token: ").strip()

    results = {}

    try:
        if not migrator.complete_login(source_token, target_token):
            results["error"] = "Login failed"
            return

        print("\nSelect data to migrate:")
        migrate_pub_follow = input("Migrate public follows? (Y/n): ").strip().lower() != "n"
        migrate_priv_follow = input("Migrate private follows? (Y/n): ").strip().lower() != "n"
        migrate_pub_bookmark = input("Migrate public bookmarks? (Y/n): ").strip().lower() != "n"
        migrate_priv_bookmark = input("Migrate private bookmarks? (Y/n): ").strip().lower() != "n"
        if not any([migrate_pub_follow, migrate_priv_follow, migrate_pub_bookmark, migrate_priv_bookmark]):
            results["error"] = "No migration tasks selected"
            return

        # ============================
        # PHASE 1: EXTRACT SOURCE DATA
        # ============================
        print("\n" + "=" * 50)
        print("→ PHASE 1: Extracting source account data")
        print("-" * 50)

        source_data = {"following": [], "bookmarks": {}}

        # Extract follows
        if migrate_pub_follow or migrate_priv_follow:
            if migrate_pub_follow:
                pub = migrator.extract_following_list(migrator.source_user_id, "public")
                if pub is not None:
                    source_data["following"].extend(pub)
            if migrate_priv_follow:
                priv = migrator.extract_following_list(migrator.source_user_id, "private")
                if priv is not None:
                    source_data["following"].extend(priv)

        # Extract bookmarks
        if migrate_pub_bookmark or migrate_priv_bookmark:
            for restrict_type, should in [("public", migrate_pub_bookmark), ("private", migrate_priv_bookmark)]:
                if should:
                    bm = migrator.extract_bookmarks(migrator.source_user_id, restrict_type)
                    if bm is not None:
                        source_data["bookmarks"][restrict_type] = bm

        # ==============================
        # PHASE 2: PREPARE DEDUPLICATION
        # ==============================
        need_follows = len(source_data["following"]) > 0
        need_bookmarks = len(source_data["bookmarks"]) > 0
        if need_follows or need_bookmarks:
            migrator.prepare_dedup_data(need_follows=need_follows, need_bookmarks=need_bookmarks)

        # =========================
        # PHASE 3: START MIGRATION
        # =========================
        print("=" * 50)
        print("→ PHASE 3: Starting migration")
        print("-" * 50)

        # Migrate follows
        if source_data["following"]:
            success, failed = migrator.migrate_following(source_data["following"])
            results["following"] = {
                "success": success,
                "total": len(source_data["following"]),
                "failed": failed
            }

        # Migrate bookmarks
        if source_data["bookmarks"]:
            results["bookmarks"] = {}
            for restrict_type, bookmarks in source_data["bookmarks"].items():
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
        print("Done.")


if __name__ == "__main__":
    main()
