import os
import subprocess

def update_container_app():
    env_file = ".env"
    if not os.path.exists(env_file):
        print("Error: .env file not found")
        return

    env_vars = []
    with open(env_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, value = line.split("=", 1)
                env_vars.append(f"{key}={value}")

    # Join the vars for the command
    env_str = " ".join(env_vars)
    
    command = [
        "az", "containerapp", "update",
        "--name", "theogen-backend",
        "--resource-group", "theogen-rg-eastus",
        "--set-env-vars"
    ] + env_vars

    print("Running command to update environment variables...")
    # Using subprocess.run with the list of arguments to avoid shell quoting issues
    result = subprocess.run(command, capture_output=True, text=True)
    
    if result.returncode == 0:
        print("Successfully updated environment variables for theogen-backend!")
    else:
        print("Error updating environment variables:")
        print(result.stderr)

if __name__ == "__main__":
    update_container_app()
