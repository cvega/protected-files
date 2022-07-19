import time


from flask import Flask, request
import jwt
import requests
from yaml import load, SafeLoader


app = Flask(__name__)


@app.route("/health")
def health():
    return dict(message="ok")


@app.route("/webhook", methods=["POST"])
def webhook():
    data = {
        "head_sha": request.json["pull_request"]["head"]["sha"],
        "number": request.json["pull_request"]["number"],
        "full_name": request.json["pull_request"]["head"]["repo"]["full_name"],
        "user": request.json["pull_request"]["user"]["login"],
        "token": GitHubAuthentication(config).auth_token(),
    }

    create = check_run_create(data)
    files = config["files"]
    owners = config["owners"]

    # match files modified in the pr against protected files
    protected_files = []
    for i in pr_files(data):
        if i["filename"] in files:
            protected_files.append(i["filename"])

    # if workflows found, validate against owners. If the owner is not in the
    # owners list, fail the check run and provide messaging. If no workflows
    # found, skip the check run.
    if len(protected_files) > 0:
        if data["user"] in owners:
            check_run_update(create["id"], "success", data, protected_files)
        else:
            check_run_update(create["id"], "failure", data, protected_files)
    else:
        check_run_update(create["id"], "skipped", data)

    return "200"


def load_yaml(file):
    with open(file, "r") as stream:
        return load(stream, Loader=SafeLoader)


def header(token):
    return {"Authorization": f"Bearer {token}"}


def pr_files(meta):
    return requests.get(
        f'{config["url"]}/repos/{meta["full_name"]}/pulls/{meta["number"]}/files',
        headers=header(meta["token"]),
    ).json()


def check_run_create(meta):
    return requests.post(
        f'{config["url"]}/repos/{meta["full_name"]}/check-runs',
        json={
            "name": config["name"],
            "head_sha": f'{meta["head_sha"]}',
            "status": "in_progress",
        },
        headers=header(meta["token"]),
    ).json()


def check_run_update(check_run_id, conclusion, meta, files=None):

    if conclusion == "success":
        summary = f'''
        {meta["user"]} is authorized to modify protected files in this pull request: 
        `{*files,}`
        '''
    elif conclusion == "failure":
        summary = f'''
        {meta["user"]} is not authorized to modify protected files in this pull request: 
        `{*files,}`
        '''
    elif conclusion == "skipped":
        summary = f'''
        No protected files found in this pull request.
        '''

    data = {
        "status": "completed",
        "name": "Protected Files",
        "output": {
            "title": "Protected Files",
            "summary": summary,
        },
        "conclusion": conclusion
    }

    return requests.patch(
        f'{config["url"]}/repos/{meta["full_name"]}/check-runs/{check_run_id}',
        json=data,
        headers=header(meta["token"]),
    ).json()


class GitHubAuthentication:
    def __init__(self, config):
        for attr, value in config.items():
            setattr(self, attr, value)

    def auth_token(self, expiration=60):
        pem = open(self.pem, "r").read()
        now = int(time.time())
        payload = {"iat": now, "exp": now + expiration, "iss": self.app_id}
        jwt_token = jwt.encode(payload, key=pem, algorithm="RS256")
        req = requests.post(
            f"{self.url}/app/installations/{self.installation_id}/access_tokens",
            headers=header(jwt_token),
        )
        resp = req.json()
        return resp["token"]


config = load_yaml("config.yml")


if __name__ == "__main__":

    app.run(host="0.0.0.0", debug=False, port=8443)
