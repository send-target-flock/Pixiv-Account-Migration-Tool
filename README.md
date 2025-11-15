# Pixiv Account Migration Tool

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

A robust, command-line tool to migrate follows and bookmarks between Pixiv accounts — with smart deduplication, rate-limit resilience, and full chronological order preservation.

⚠️ **Disclaimer**: This tool uses the Pixiv API via [`PixivPy3`](https://github.com/upbit/pixivpy "PixivPy3"). Ensure compliance with [`Pixiv's Terms of Service`](https://www.pixiv.net/terms/).

---

## ✨ Features

- **Follow & Bookmark Migration**: Transfer public/private follows and bookmarks.
- **Smart Deduplication**: Skip items already present in the target account.
- **Chronological Integrity**: Migrates oldest-first to preserve timeline order.
- **Rate-Limit Resilience**: Automatic retry on `Rate Limit` errors (configurable).
- **Comprehensive Reporting**: Generates detailed success/failure report on every run — even on crash or interruption.
- **Fully Configurable**: Adjust delays, retries, and behavior via intuitive CLI prompts.

---

## 🛠️ Requirements

- Python 3.7+
- Valid Pixiv `refresh_token` for **both** source and target accounts  
  (See [`PixivPy3's README`](https://github.com/upbit/pixivpy/blob/master/README.md) for instruction)
> 🛡️ **Security Note**: Treat `refresh_token` like a password. Do not share it with others.

---

## 📦 Installation

```bash
# Clone the repository
git clone https://github.com/send-target-flock/Pixiv-Account-Migration-Tool
cd Pixiv-Account-Migration-Tool

# Install dependencies
pip install pixivpy3
```

---

## ▶️ Usage

```bash
python migration.py
```

Follow the interactive prompts:
1. Set configuration (delays, retries — defaults optimized for stability)
2. Enter `refresh_token` for source and target accounts
3. Select data to migrate (public/private follows & bookmarks)
4. Wait for completion — a report file (`migration_report_YYYYMMDD_HHMMSS.txt`) is generated automatically.

> 💡 **Tip**: If migration is interrupted, simply re-run the script. Deduplication ensures only missing items are processed.

---

## ⚙️ Configuration Options

| Parameter | Description | Default |
|-----------|-------------|---------|
| `extract_delay` | Delay (seconds) between data extraction requests | `1.0` |
| `migrate_delay` | Base delay (seconds) between migration actions | `2.5` |
| `max_retries` | Max retries on rate limit (`-1` = infinite) | `-1` |
| `retry_wait` | Wait time (seconds) before retrying | `60` |

---

## 📄 Report Output

After each run (success or failure), a timestamped report is saved, e.g.:

```
migration_report_20251115_143022.txt
```

It includes:
- Migration timestamp
- Summary of succeeded/failed items
- Detailed list of failed follows (name, account, visibility)
- Detailed list of failed bookmarks (title, author, visibility)
- Termination reason (e.g., *Login failed*, *Interrupted by user*)

---

## 📜 License

MIT License — see [LICENSE](LICENSE) for details.

---

## 🙏 Acknowledgements

- [`pixivpy3`](https://github.com/upbit/pixivpy) — Python wrapper for Pixiv API
- LLMs for coding support
