#!/usr/bin/env python3
import uuid
from flask import Flask, request, Response, jsonify
from flask_basicauth import BasicAuth
from natsort import natsort_keygen, ns

from .config import Config
config = Config()

app = Flask(__name__)

@app.get("/")
def home():
    return "<html><body><h1>scrapyd-k8s</h1></body></html>"

@app.get("/healthz")
def healthz():
    return "OK", 200

@app.get("/daemonstatus.json")
def api_daemonstatus():
    jobs = list(config.launcher().listjobs())
    return {
        "node_name": config.scrapyd().get("node_name", config.launcher().get_node_name()),
        "status": "ok",
        "pending": len([j for j in jobs if j['state'] == 'pending']),
        "running": len([j for j in jobs if j['state'] == 'running']),
        "finished": len([j for j in jobs if j['state'] == 'finished'])
    }

@app.post("/schedule.json")
def api_schedule():
    project_id = request.form.get('project')
    if not project_id:
        return error('project missing in form parameters', status=400)
    project = config.project(project_id)
    if not project:
        return error('project not found in configuration', status=400)
    spider = request.form.get('spider')
    if not spider:
        return error('spider not found in form parameters', status=400)
    settings = dict(x.split('=', 1) for x in request.form.getlist('setting'))
    job_id = request.form.get('jobid', uuid.uuid1().hex)
    # priority = request.form.get('priority') or 0 # TODO implement priority
    _version = request.form.get('_version', 'latest') # TODO allow customizing latest tag
    # any other parameter is passed as spider argument
    args = { k: v for k, v in request.form.items() if k not in ('project', 'spider', 'setting', 'jobid', 'priority', '_version') }
    env_config, env_secret = project.env_config(), project.env_secret()
    jobid = config.launcher().schedule(project, _version, spider, job_id, settings, args)
    return { 'status': 'ok', 'jobid': job_id }

@app.post("/cancel.json")
def api_cancel():
    project_id = request.form.get('project')
    if not project_id:
        return error('project missing in form parameters', status=400)
    job_id = request.form.get('job')
    if not job_id:
        return error('job missing in form parameters', status=400)
    signal = request.form.get('signal', 'TERM') # TODO validate signal?
    prevstate = config.launcher().cancel(project_id, job_id, signal)
    if not prevstate:
        return error('job not found', status=404)
    return { 'status': 'ok', 'prevstate': prevstate }

@app.get("/listprojects.json")
def api_listprojects():
    return { 'status': 'ok', 'projects': config.listprojects() }

@app.get("/listversions.json")
def api_listversions():
    project_id = request.args.get('project')
    if not project_id:
        return error('project missing in query parameters', status=400)
    project = config.project(project_id)
    if not project:
        return error('project not found in configuration', status=404)
    tags = config.repository().listtags(project.repository())
    tags = [t for t in tags if not t.startswith('sha-')]
    tags.sort(key=natsort_keygen(alg=ns.NUMAFTER))
    return { 'status': 'ok', 'versions': tags }

@app.get("/listspiders.json")
def api_listspiders():
    project_id = request.args.get('project')
    if not project_id:
        return error('project missing in query parameters', status=400)
    project = config.project(project_id)
    if not project:
        return error('project not found in configuration', status=404)
    _version = request.args.get('_version', 'latest') # TODO allow customizing latest tag
    spiders = config.repository().listspiders(project.repository(), project_id, _version)
    if spiders is None:
        return error('project version not found in repository', status=404)
    return { 'status': 'ok', 'spiders': spiders }

@app.get("/listjobs.json")
def api_listjobs():
    project_id = request.args.get('project')
    jobs = config.launcher().listjobs(project_id)
    pending = [j for j in jobs if j['state'] == 'pending']
    running = [j for j in jobs if j['state'] == 'running']
    finished = [j for j in jobs if j['state'] == 'finished']
    # TODO perhaps remove state from jobs
    return { 'status': 'ok', 'pending': pending, 'running': running, 'finished': finished }

@app.post("/addversion.json")
def api_addversion():
    return error("Not supported, by design. If you want to add a version, "
                 "add a Docker image to the repository.", status=501)

@app.post("/delversion.json")
def api_delversion():
    return error("Not supported, by design. If you want to delete a version, "
                 "remove the corresponding Docker image from the repository.", status=501)

@app.post("/delproject.json")
def api_delproject():
    return error("Not supported, by design. If you want to delete a project, "
                 "remove it from the configuration file.", status=501)

# middleware that adds "node_name" to each response if it is a JSON
@app.after_request
def after_request(response: Response):
    if response.is_json:
        data = response.json
        data["node_name"] = config.scrapyd().get("node_name", config.launcher().get_node_name())
        response.data = jsonify(data).data
    return response

def error(msg, status=200):
    return { 'status': 'error', 'message': msg }, status

def enable_authentication(app, config_username, config_password):

    # workaround for https://github.com/jpvanhal/flask-basicauth/issues/11
    class BasicAuthExceptHealthz(BasicAuth):
        def authenticate(self):
            return request.path == "/healthz" or super().authenticate()

    basic_auth = BasicAuthExceptHealthz(app)
    app.config["BASIC_AUTH_USERNAME"] = config_username
    app.config["BASIC_AUTH_PASSWORD"] = config_password
    app.config["BASIC_AUTH_FORCE"] = True
    return basic_auth

def run():
    scrapyd_config = config.scrapyd()

    # where to listen
    host = scrapyd_config.get('bind_address', '127.0.0.1')
    port = scrapyd_config.get('http_port', '6800')

    # authentication
    config_username = scrapyd_config.get('username')
    config_password = scrapyd_config.get('password')
    if config_username is not None and config_password is not None:
        enable_authentication(app, config_username, config_password)

    # run server
    app.run(host=host, port=port)
