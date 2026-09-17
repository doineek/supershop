"""
release_build.py
----------------
Fully Automated APK Build & GitHub Release Tool for SuperShop.

Usage:
    python release_build.py
    python release_build.py --token YOUR_GITHUB_TOKEN
    python release_build.py --local-build

Features:
1. Automatically reads the version from supershop_flutter_app/pubspec.yaml
2. Uploads the 54 MB APK directly to GitHub Releases via GitHub API
3. Sets it as the "latest" release
4. Customers tapping "Download APK" will download from high-speed GitHub CDN
5. Saves 100% of Render free bandwidth on every customer download!
"""

import os
import sys
import json
import argparse
import requests

REPO = "doineek/supershop"
TOKEN_FILE = ".github_token"

def get_pubspec_version():
    pubspec = os.path.join("supershop_flutter_app", "pubspec.yaml")
    if not os.path.exists(pubspec):
        return None
    with open(pubspec, "r", encoding="utf-8") as f:
        for line in f:
            line_str = line.strip()
            if line_str.startswith("version:"):
                val = line_str.split(":", 1)[1].strip().strip('"').strip("'")
                return val.split("+")[0].strip()
    return None

def get_git_credential_token():
    try:
        import subprocess
        proc = subprocess.Popen(
            ["git", "credential", "fill"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        out, _ = proc.communicate(input="protocol=https\nhost=github.com\nusername=doineek\n", timeout=5)
        for line in out.splitlines():
            if line.startswith("password="):
                tok = line.split("=", 1)[1].strip()
                if tok.startswith("ghp_") or tok.startswith("github_pat_"):
                    return tok
    except Exception:
        pass
    return None

def get_token(cli_token=None):
    if cli_token:
        return cli_token.strip()
    if os.environ.get("GITHUB_TOKEN"):
        return os.environ.get("GITHUB_TOKEN").strip()
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "r", encoding="utf-8") as f:
            t = f.read().strip()
            if t:
                return t
    git_tok = get_git_credential_token()
    if git_tok:
        return git_tok
    return None

def save_token(token):
    try:
        with open(TOKEN_FILE, "w", encoding="utf-8") as f:
            f.write(token.strip())
        print(f"[OK] Token saved to {TOKEN_FILE} for future releases.")
    except Exception as e:
        print(f"Warning: could not save token: {e}")

def upload_apk_to_github(token, tag, apk_path, asset_name):
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "SuperShop-AutoReleaser"
    }

    print(f"\n[1/2] Connecting to GitHub Releases for {REPO} ({tag})...")
    rel_url = f"https://api.github.com/repos/{REPO}/releases"
    res = requests.get(f"{rel_url}/tags/{tag}", headers=headers)

    if res.status_code == 200:
        rel_data = res.json()
        print(f"Found existing release for {tag} (ID: {rel_data['id']})")
    else:
        print(f"Creating new GitHub Release: {tag}...")
        payload = {
            "tag_name": tag,
            "target_commitish": "main",
            "name": f"SuperShop Android v{tag.lstrip('v')}",
            "body": f"Official release for Android APK ({tag}). Direct CDN download available.",
            "draft": False,
            "prerelease": False,
            "make_latest": "true"
        }
        create_res = requests.post(rel_url, headers=headers, json=payload)
        if create_res.status_code not in (200, 201):
            print(f"Failed to create release: {create_res.status_code} - {create_res.text}")
            return False
        rel_data = create_res.json()
        print(f"Created release successfully (ID: {rel_data['id']})")

    upload_url = rel_data["upload_url"].split("{")[0]

    # Delete existing asset with same name if already present
    for asset in rel_data.get("assets", []):
        if asset["name"] == asset_name:
            print(f"Replacing existing asset: {asset_name}...")
            requests.delete(asset["url"], headers=headers)
            break

    file_size_mb = os.path.getsize(apk_path) / (1024 * 1024)
    print(f"\n[2/2] Uploading {asset_name} ({file_size_mb:.1f} MB) directly to GitHub Releases...")
    
    with open(apk_path, "rb") as f:
        up_headers = {
            "Authorization": f"token {token}",
            "Content-Type": "application/vnd.android.package-archive",
            "User-Agent": "SuperShop-AutoReleaser"
        }
        up_res = requests.post(
            f"{upload_url}?name={asset_name}",
            headers=up_headers,
            data=f
        )
        if up_res.status_code in (200, 201):
            print(f"[SUCCESS] Uploaded {asset_name} successfully!")
            return True
        else:
            print(f"[FAIL] Upload failed: {up_res.status_code} - {up_res.text}")
            return False

def main():
    parser = argparse.ArgumentParser(description="SuperShop Automated APK Release Tool")
    parser.add_argument("--token", type=str, help="GitHub Personal Access Token (PAT)")
    parser.add_argument("--tag", type=str, help="Release tag name (e.g. v1.0.11)")
    parser.add_argument("--local-build", action="store_true", help="Run 'flutter build apk --release' first")
    args = parser.parse_args()

    version = get_pubspec_version()
    tag = args.tag or (f"v{version}" if version else None)
    if not tag:
        print("Error: Could not determine version from pubspec.yaml.")
        sys.exit(1)

    if not tag.startswith("v"):
        tag = f"v{tag}"

    print("=" * 60)
    print(f"  SuperShop Automated APK Releaser: {tag}")
    print("=" * 60)

    # Locate APK file
    apk_path = os.path.join("static", "apk", "supershop_latest.apk")
    flutter_apk = os.path.join("supershop_flutter_app", "build", "app", "outputs", "flutter-apk", "app-release.apk")
    
    if args.local_build:
        print("\nBuilding Flutter release APK locally...")
        res = os.system("cd supershop_flutter_app && flutter build apk --release")
        if res != 0:
            print("Flutter build failed!")
            sys.exit(1)

    if os.path.exists(flutter_apk):
        apk_path = flutter_apk
    elif not os.path.exists(apk_path):
        print(f"Error: APK file not found at {apk_path} or {flutter_apk}")
        sys.exit(1)

    # Retrieve GitHub Token
    token = get_token(args.token)
    if not token:
        print("\nGitHub Personal Access Token is required to upload the APK automatically.")
        print("You can generate one with 'repo' scope at: https://github.com/settings/tokens/new")
        try:
            token = input("\nEnter your GitHub Token: ").strip()
        except Exception:
            pass

    if not token:
        print("Error: No GitHub token provided. Aborting.")
        sys.exit(1)

    save_token(token)

    # Also sync all local static APK filenames
    try:
        import shutil
        apk_dir = os.path.join("static", "apk")
        os.makedirs(apk_dir, exist_ok=True)
        shutil.copy2(apk_path, os.path.join(apk_dir, "supershop_latest.apk"))
        shutil.copy2(apk_path, os.path.join(apk_dir, "doineek_latest.apk"))
        shutil.copy2(apk_path, os.path.join(apk_dir, f"doineek_{tag}.apk"))
        shutil.copy2(apk_path, os.path.join(apk_dir, f"supershop_{tag}.apk"))
        print("[OK] Synchronized all local static/apk files.")
    except Exception as e:
        print(f"Warning: could not copy local APKs: {e}")

    # Upload APK as doineek_{tag}.apk, doineek_latest.apk, supershop_latest.apk, supershop_{tag}.apk
    success = upload_apk_to_github(token, tag, apk_path, f"doineek_{tag}.apk")
    if success:
        upload_apk_to_github(token, tag, apk_path, "doineek_latest.apk")
        upload_apk_to_github(token, tag, apk_path, "supershop_latest.apk")
        upload_apk_to_github(token, tag, apk_path, f"supershop_{tag}.apk")

        # Auto-update version.json and database settings
        try:
            ver_clean = tag.lstrip("v")
            v_json = os.path.join("static", "flutter_web", "version.json")
            if os.path.exists(os.path.dirname(v_json)):
                with open(v_json, "w", encoding="utf-8") as vf:
                    json.dump({"app_name": "supershop_app", "version": ver_clean, "build_number": "", "package_name": "supershop_app"}, vf)
            import database
            conn = database.get_connection()
            database.update_settings(conn, {
                "app_version": f"v{ver_clean}",
                "app_version_short": f"v{ver_clean}",
                "app_version_full": f"Version {ver_clean} • Official Release",
                "app_version_num": ver_clean,
                "apk_download_url": f"https://github.com/{REPO}/releases/download/{tag}/doineek_{tag}.apk"
            })
            conn.close()
            print("[OK] Local settings and static/flutter_web/version.json updated.")
        except Exception as ex:
            print(f"Note: local sync skipped: {ex}")

        print("\n" + "=" * 60)
        print("  ALL DONE! Release is Live on GitHub CDN")
        print("=" * 60)
        print(f"Release Tag: {tag}")
        print(f"Versioned Download URL: https://github.com/{REPO}/releases/download/{tag}/doineek_{tag}.apk")
        print(f"Permanent Download URL: https://github.com/{REPO}/releases/latest/download/doineek_latest.apk")
        print(f"Render Bandwidth Consumed: 0 MB (100% saved!)")
        print("=" * 60)

if __name__ == "__main__":
    main()
