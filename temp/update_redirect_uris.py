import subprocess
import json

# First, get the object ID
result = subprocess.run(
    ["az", "ad", "app", "show", "--id", "c6d2cf71-dcd2-4400-a8be-9eb8c16b1174", "--query", "id", "-o", "tsv"],
    capture_output=True, text=True, shell=True
)
object_id = result.stdout.strip()
print(f"Object ID: {object_id}")

if not object_id:
    print("Error getting object ID:", result.stderr)
    exit(1)

# Update the app using the object ID
body = {
    "spa": {
        "redirectUris": [
            "https://theogenfrontwpdxe2pv.z13.web.core.windows.net/",
            "https://theogenfrontpllrx4ji.z13.web.core.windows.net/",
            "https://theogenfrontpllrx4ji.z13.web.core.windows.net/login/",
            "https://theogenfrontwpdxe2pv.z13.web.core.windows.net/login/",
            "http://localhost:3000/",
            "http://localhost:3000/login/"
        ]
    }
}

body_str = json.dumps(body)

# Use Graph API with object ID
uri = f"https://graph.microsoft.com/v1.0/applications/{object_id}"

result = subprocess.run(
    ["az", "rest", "--method", "PATCH", "--uri", uri, "--body", body_str],
    capture_output=True, text=True, shell=True
)

print("STDOUT:", result.stdout)
print("STDERR:", result.stderr)
print("Return code:", result.returncode)

# Verify the update
result2 = subprocess.run(
    ["az", "ad", "app", "show", "--id", "c6d2cf71-dcd2-4400-a8be-9eb8c16b1174", "--query", "spa.redirectUris", "-o", "json"],
    capture_output=True, text=True, shell=True
)
print("Current URIs:", result2.stdout)
