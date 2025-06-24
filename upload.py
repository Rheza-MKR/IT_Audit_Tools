import os
import requests
from dotenv import load_dotenv

load_dotenv()

TABLEAU_SERVER = os.getenv('TABLEAU_SERVER')
TABLEAU_SITE = os.getenv('TABLEAU_SITE')
TABLEAU_USERNAME = os.getenv('TABLEAU_USERNAME')
TABLEAU_PASSWORD = os.getenv('TABLEAU_PASSWORD')
TABLEAU_PROJECT_ID = os.getenv('TABLEAU_PROJECT_ID')

console_url = f"{TABLEAU_SERVER}/api/3.18/auth/signin"

def sign_in():
    """Sign in to Tableau Cloud and get authentication token."""
    payload = {
        "credentials": {
            "name": TABLEAU_USERNAME,
            "password": TABLEAU_PASSWORD,
            "site": {"contentUrl": TABLEAU_SITE}
        }
    }

    response = requests.post(console_url, json=payload)
    response.raise_for_status()

    auth_token = response.json()['credentials']['token']
    site_id = response.json()['credentials']['site']['id']
    user_id = response.json()['credentials']['user']['id']

    return auth_token, site_id, user_id

def upload_data_source(auth_token, site_id, csv_path, datasource_name):
    """Upload CSV as a data source to Tableau Cloud."""
    url = f"{TABLEAU_SERVER}/api/3.18/sites/{site_id}/fileUploads"
    headers = {"X-Tableau-Auth": auth_token}

    # Upload file chunk (Tableau requires multipart upload)
    with open(csv_path, 'rb') as file:
        files = {'file': (os.path.basename(csv_path), file, 'application/octet-stream')}
        upload_response = requests.post(url, headers=headers, files=files)
        upload_response.raise_for_status()

    upload_session_id = upload_response.json()['fileUpload']['uploadSessionId']

    # Create the data source
    publish_url = f"{TABLEAU_SERVER}/api/3.18/sites/{site_id}/datasources?uploadSessionId={upload_session_id}&datasourceType=textscan&overwrite=true"
    payload = {
        "datasource": {
            "name": datasource_name,
            "project": {"id": TABLEAU_PROJECT_ID}
        }
    }

    publish_response = requests.post(publish_url, headers=headers, json=payload)
    publish_response.raise_for_status()

    console.print(f"[bold green] Uploaded successfully: {datasource_name}[/bold green]")

def sign_out(auth_token):
    """Sign out to invalidate the session."""
    sign_out_url = f"{TABLEAU_SERVER}/api/3.18/auth/signout"
    headers = {"X-Tableau-Auth": auth_token}
    requests.post(sign_out_url, headers=headers)

def main():
    from rich.console import Console
    console = Console()

    console.print("[bold cyan]📤 Tableau Cloud CSV Uploader[/bold cyan]")

    csv_path = input("Enter the path to the CSV file: ")
    datasource_name = input("Enter the desired data source name: ")

    try:
        auth_token, site_id, user_id = sign_in()
        console.print("[bold green] Signed in successfully[/bold green]")

        upload_data_source(auth_token, site_id, csv_path, datasource_name)
        sign_out(auth_token)
        console.print("[bold green] Signed out successfully[/bold green]")

    except Exception as e:
        console.print(f"[bold red] Upload failed: {e}[/bold red]")

if __name__ == "__main__":
    main()
