import os
import hashlib
import hmac
import datetime
import requests

CF_ACCOUNT_ID = os.environ.get("CF_ACCOUNT_ID", "42f65e201d7d14e78cac87e1f1027b18")
CF_R2_ACCESS_KEY_ID = os.environ.get("CF_R2_ACCESS_KEY_ID", "20a6ea7c1fb42e580233c48f5095edda")
CF_R2_SECRET_ACCESS_KEY = os.environ.get("CF_R2_SECRET_ACCESS_KEY", "dc0787ad260789f2705160e9eb39ec6b9ece1ddc33de5b23a8b5945df8e31be1")
CF_R2_BUCKET = os.environ.get("CF_R2_BUCKET", "supershop-prescriptions")
CF_R2_PUBLIC_DOMAIN = os.environ.get("CF_R2_PUBLIC_DOMAIN", "").strip().rstrip("/")

def _sign(key, msg):
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()

def _get_signature_key(key, date_stamp, region_name, service_name):
    k_date = _sign(("AWS4" + key).encode("utf-8"), date_stamp)
    k_region = _sign(k_date, region_name)
    k_service = _sign(k_region, service_name)
    k_signing = _sign(k_service, "aws4_request")
    return k_signing

def upload_to_r2(data_bytes, filename, content_type="image/jpeg"):
    """
    Uploads raw bytes to Cloudflare R2 bucket using AWS SigV4.
    Returns (public_url, filename) on success, or (None, None) on failure.
    Zero egress fee, preserving Render's 5GB bandwidth completely.
    """
    if not (CF_ACCOUNT_ID and CF_R2_ACCESS_KEY_ID and CF_R2_SECRET_ACCESS_KEY):
        return None, None

    host = f"{CF_ACCOUNT_ID}.r2.cloudflarestorage.com"
    region = "auto"
    service = "s3"

    now = datetime.datetime.now(datetime.timezone.utc)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")

    # Target path: /bucket/filename
    clean_filename = filename.lstrip("/")
    canonical_uri = f"/{CF_R2_BUCKET}/{clean_filename}"
    canonical_querystring = ""

    payload_hash = hashlib.sha256(data_bytes).hexdigest()
    canonical_headers = (
        f"content-type:{content_type}\n"
        f"host:{host}\n"
        f"x-amz-content-sha256:{payload_hash}\n"
        f"x-amz-date:{amz_date}\n"
    )
    signed_headers = "content-type;host;x-amz-content-sha256;x-amz-date"

    canonical_request = (
        f"PUT\n"
        f"{canonical_uri}\n"
        f"{canonical_querystring}\n"
        f"{canonical_headers}\n"
        f"{signed_headers}\n"
        f"{payload_hash}"
    )

    algorithm = "AWS4-HMAC-SHA256"
    credential_scope = f"{date_stamp}/{region}/{service}/aws4_request"
    string_to_sign = (
        f"{algorithm}\n"
        f"{amz_date}\n"
        f"{credential_scope}\n"
        f"{hashlib.sha256(canonical_request.encode('utf-8')).hexdigest()}"
    )

    signing_key = _get_signature_key(CF_R2_SECRET_ACCESS_KEY, date_stamp, region, service)
    signature = hmac.new(signing_key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

    auth_header = (
        f"{algorithm} Credential={CF_R2_ACCESS_KEY_ID}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )

    headers = {
        "Host": host,
        "Content-Type": content_type,
        "x-amz-date": amz_date,
        "x-amz-content-sha256": payload_hash,
        "Authorization": auth_header,
        "Cache-Control": "public, max-age=31536000, immutable"
    }

    url = f"https://{host}{canonical_uri}"

    try:
        resp = requests.put(url, headers=headers, data=data_bytes, timeout=12)
        if resp.status_code in [200, 201]:
            if CF_R2_PUBLIC_DOMAIN:
                public_url = f"{CF_R2_PUBLIC_DOMAIN}/{clean_filename}"
            else:
                # Default Cloudflare R2 dev or proxy URL
                public_url = f"https://{CF_ACCOUNT_ID}.r2.cloudflarestorage.com/{CF_R2_BUCKET}/{clean_filename}"
            print(f"[cloudflare_r2] [OK] Uploaded {clean_filename} to R2: {public_url}")
            return public_url, clean_filename
        else:
            print(f"[cloudflare_r2] Upload failed ({resp.status_code}): {resp.text[:200]}")
            return None, None
    except Exception as e:
        print(f"[cloudflare_r2] Error uploading to R2: {e}")
        return None, None
