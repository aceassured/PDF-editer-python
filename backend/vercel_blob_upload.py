import requests


def upload_to_vercel_blob(file):
    upload_url = "https://blob.vercel-storage.com/upload"  # adjust if needed
    files = {"file": (file.filename, file.stream, file.content_type)}

    response = requests.post(upload_url, files=files)
    response.raise_for_status()

    data = response.json()
    return data['url']
