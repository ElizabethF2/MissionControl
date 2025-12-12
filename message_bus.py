# A simple, RESTful message bus
# If USE_MULTITHREADING is true, long polling will be enabled
# When deploying, ensure only a single instance is running and
# that the same instance will be used across multiple requests

import sys, os, json, threading, http.server, socketserver, urllib.parse

def _load_config():
  config_defaults = {
    'port': (int, 80),
    'use_multithreading': (int, 1),
    'wait_timeout': (float, 28),
    'magic_recipients': (json.loads, '{}'),
    'max_size': (int, 150*1024*1024),
    'check_size': (int, 0),
    'certfile': (lambda i: i, None),
    'keyfile': (lambda i: i, None),
  }
  config = {
    name: d[0](os.environ.get(name.upper(), d[1]))
    for name, d in config_defaults.items()
  }
  if config_path := os.environ.get('MCBUS_CONFIG'):
    with open(config_path, 'r') as f:
      config |= json.load(f)
  for k, v in config.items():
    globals()[k.upper()] = v

_load_config()
del _load_config()

LOCK = threading.Lock()
INBOXES = {}
INBOX_EVENTS = {}

def get_size(obj):
  size = 0
  if type(obj) is dict:
    size += sum((get_size(k) + get_size(v) for k,v in obj.items()))
  elif type(obj) is list:
    size += sum(map(get_size, obj))
  else:
    return sys.getsizeof(obj)
  return size

def ensure_inboxes_under_max_size_with_lock():
  if CHECK_SIZE and (get_size(INBOXES) + get_size(INBOX_EVENTS)) > MAX_SIZE:
    INBOXES.clear()
    INBOXE_EVENTS.clear()

def get_or_create_inbox_event(name):
  with LOCK:
    event = INBOX_EVENTS.get(name)
    if event:
      return event
    return INBOX_EVENTS.setdefault(name, threading.Event())

class RequestHandler(http.server.BaseHTTPRequestHandler):
  def respond(self, result):
    resp = json.dumps(result).encode()
    self.send_response(200)
    self.send_header('Content-Type', 'application/json')
    self.send_header('Content-Length', str(len(resp)))
    self.send_header('Access-Control-Allow-Origin', '*')
    self.end_headers()
    self.wfile.write(resp)

  # Handle CORS preflight
  def do_OPTIONS(self):
    self.send_response(204)
    self.send_header('Access-Control-Allow-Origin', '*')
    self.send_header('Access-Control-Allow-Headers', '*')
    self.send_header('Access-Control-Allow-Methods', 'POST, GET, OPTIONS')
    self.end_headers()

  # Get message(s)
  def do_GET(self):
    result = []
    qs = {
      k:v[0] for k,v in
      urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).items()
    }
    name = qs.get('name')
    if name:
      if USE_MULTITHREADING:
        event = get_or_create_inbox_event(name)
        event.wait(timeout=WAIT_TIMEOUT)
        event.clear()
      with LOCK:
        ensure_inboxes_under_max_size_with_lock()
        if name in INBOXES:
          result = INBOXES.pop(name)
    self.respond(result)

  # Send a message
  def do_POST(self):
    try:
      content_len = int(self.headers.get('content-length', 0))
      message = json.loads(self.rfile.read(content_len))
      if type(message['recipient']) is not str:
        return self.respond(False)
      recipient = message.pop('recipient')
      recipient = MAGIC_RECIPIENTS.get(recipient, recipient)
      with LOCK:
        ensure_inboxes_under_max_size_with_lock()
        INBOXES.setdefault(recipient, []).append(message)
      if USE_MULTITHREADING:
        get_or_create_inbox_event(recipient).set()
      return self.respond(True)
    except:
      return self.respond(False)

class MultiThreadedServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
  daemon_thread = True

def main():
  if USE_MULTITHREADING:
    httpd = MultiThreadedServer(('', PORT), RequestHandler)
  else:
    httpd = http.server.HTTPServer(('', PORT), RequestHandler)

  if CERTFILE:
    import ssl
    context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    context.load_cert_chain(CERTFILE, keyfile = KEYFILE)
    httpd.socket = context.wrap_socket(httpd.socket, server_side = True)

  httpd.serve_forever()

if __name__ == '__main__':
  main()
