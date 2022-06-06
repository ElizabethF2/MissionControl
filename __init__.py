import requests, json, os, threading, time, subprocess, io, binascii
import api_backend

# TODO: Add a config var to poll the bus and sleep w/ a backoff that can be enabled for message buses run w/ USE_MULTITHREADING set to false

NETWORK_ERRORS = (ConnectionError, json.decoder.JSONDecodeError, requests.exceptions.ConnectionError)

LOCK = threading.Lock()
running_jobs = []

import sessen
logger = sessen.getLogger()

SCRIPT_DIR = os.path.dirname(__file__)
with open(os.path.join(SCRIPT_DIR, 'config.json'), 'r') as f:
  config = json.load(f)

def job_ouput(job, text):
  send_message({
    'recipient': job['sender'],
    'action': 'output',
    'text': job['name'] + ':' + str(job['id']) + ': ' + text
  })

def job_watcher(job):
  proc = job['proc']
  while True:
    line = proc.stdout.readline().decode().strip()
    if line.startswith('MissionControlTitle:'):
      job['title'] = line[20:].strip()
    elif line.startswith('MissionControlOutput:'):
      job_ouput(job, line[21:].strip())
    elif not line and proc.poll() is not None:
      break
  job_ouput(job, 'Terminated with return code ' + str(proc.returncode))
  with LOCK:
    temp_jobs = list(filter(lambda job: job['proc'].poll() is None, running_jobs))
    running_jobs.clear()
    running_jobs.extend(temp_jobs)

def fix_cmd(cmd):
  if type(cmd) is list:
    return list(map(fix_cmd, cmd))
  return os.path.expanduser(os.path.expandvars(cmd))

def start_job(sender, name, payload):
  job_config = load_jobs().get(name)
  if job_config:
    command = fix_cmd(job_config['command'])
    env = {k:v for k,v in os.environ.items()}
    env['MISSIONCONTROL_PAYLOAD'] = json.dumps(payload)
    job = {'name': name, 'sender': sender, 'title': None, 'start': time.time()}

    with LOCK:
      if job_config.get('singleton', True) and any((job['name'] == name for job in running_jobs)):
        send_message({'recipient': sender, 'action': 'output', 'text': 'A ' + name + ' job is already running.'})
        return
      print('MISSIONCONTROLDBG start', command)
      job['proc'] = subprocess.Popen(command,
                                     env=env,
                                     stdin = subprocess.DEVNULL,
                                     stdout = subprocess.PIPE,
                                     stderr = subprocess.DEVNULL)
      job['id'] = max((job['id'] for job in running_jobs), default=-1) + 1
      running_jobs.append(job)
    threading.Thread(target=job_watcher, args=(job,), daemon=True).start()
    job_ouput(job, 'Started')

def load_jobs():
  with open(os.path.join(SCRIPT_DIR, 'jobs.json'), 'r') as f:
    return json.load(f)

class ProxiedRequest(object):
  def __init__(self, message):
    self._sender = message.get('from')
    self._uid = str(message.get('uid') or '')
    self.path = message.get('url')
    self.command = str(message.get('method') or 'GET')
    self.status_code = None
    self.client_address = (0,0)
    self.response_headers = {}
    self.headers = str(message.get('headers') or '')
    self.wfile = io.BytesIO()
    self.rfile = io.BytesIO()
    if 'body' in message:
      self.rfile.write(message['body'].encode())
      self.rfile.seek(0)

  def __del__(self):
    if self.status_code:
      self.wfile.seek(0)
      send_message({
        'action': 'proxy',
        'recipient': self._sender,
        'uid': self._uid,
        'status_code': self.status_code,
        'headers': self.response_headers,
        'body': binascii.b2a_base64(self.wfile.read(), newline=False).decode()
      })

  def send_response(self, code):
    self.status_code = code

  def send_header(self, name, value):
    self.response_headers[name] = value

  def end_headers(self):
    pass

  def send_error(self, code):
    self.send_response(code)

def proxied_request_worker(message):
  request = ProxiedRequest(message)
  if request._uid and request.path and type(request.path) is str:
    sp = request.path.split('/')
    if len(sp) > 1:
      name = sp[1]
      if name in config['PROXIALE_EXTENSIONS']:
        api_backend._connection_route(request)

def send_message(message):
  try:
    requests.post(config['MESSAGE_BUS_URL'], json=message)
  except NETWORK_ERRORS:
    pass

def handle_message(message):
  action = message.get('action')
  sender = message.get('from')

  #logger.info('GOTMAIL:'+json.dumps(message))
  #return

  if not sender:
    return
  if action == 'queryjobs':
    jobs = load_jobs()
    queryable_jobs = [i[0] for i in filter(lambda i: i[1].get('queryable', True), jobs.items())]
    send_message({
      'recipient': sender,
      'action': 'updatejobs',
      'jobs': queryable_jobs
    })
  elif action == 'runningjobs':
    out = '\n-= Running Jobs =-\n'
    with LOCK:
      for job in running_jobs:
        out += job['name'] + ':' + str(job['id']) + (':%.2f' % (time.time()-job['start'])) + ((': '+job['title']) if job['title'] else '') + '\n'
    out += '\n'
    send_message({'recipient': sender, 'action': 'output', 'text': out})
  elif action == 'runjob':
    start_job(sender, message.get('jobname'), message.get('payload'))
  elif action == 'proxy':
    threading.Thread(target=proxied_request_worker, args=(message,), daemon=True).start()

def handle_messages_until_idle():
  last_message_time = time.time()
  while True:
    try:
      inbox = requests.get(config['MESSAGE_BUS_URL']+'?name='+config['SERVER_NAME']).json()
    except NETWORK_ERRORS:
      continue
    for message in inbox:
      print('MISSIONCONTROLDBG message', message)
      handle_message(message)
      last_message_time = time.time()
    if (time.time() - last_message_time) > config['IDLE_TIMEOUT']:
      return

def inbox_reader():
  while True:
    try:
      if config.get('USE_WAKER', True):
        try:
          print('MISSIONCONTROLDBG before waker')
          signaled = requests.get(config['WAKER_URL']+'?wait=1').json()
          print('MISSIONCONTROLDBG after waker')
        except NETWORK_ERRORS as err:
          print('MISSIONCONTROLDBG neterror', repr(err))
          time.sleep(20)
          continue
      else:
        signaled = True
      if signaled:
        print('MISSIONCONTROLDBG before handlemessages')
        handle_messages_until_idle()
        print('MISSIONCONTROLDBG after handlemessages')
    except Exception as exc:
      print('MISSIONCONTROLDBG', repr(exc))
      breakpoint()

threading.Thread(target=inbox_reader, daemon=True).start()
