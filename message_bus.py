# A simple message bus
# If USE_MULTITHREADING is true, long polling will be enabled
# When deploying, ensure only a single instance is running and that the same instance will be used accross multiple requests

import sys, os, json, threading, http.server, socketserver, urllib.parse

PORT = int(os.environ.get('PORT', 80))
USE_MULTITHREADING = int(os.environ.get('USE_MULTITHREADING', 1))
WAIT_TIMEOUT = float(os.environ.get('WAIT_TIMEOUT', 28))
MAGIC_RECIPIENTS = json.loads(os.environ.get('MAGIC_RECIPIENTS', '{}'))
MAX_SIZE = int(os.environ.get('MAX_SIZE', 150*1024*1024))
CHECK_SIZE = int(os.environ.get('CHECK_SIZE', 0))

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
    self.send_response(200)
    self.send_header('Content-type', 'application/json')
    self.send_header('Access-Control-Allow-Origin', '*')
    self.end_headers()
    self.wfile.write(json.dumps(result).encode())

  # Handle CORS preflight
  def do_OPTIONS(self):
    self.send_response(204)
    self.send_header('Access-Control-Allow-Origin', '*')
    self.send_header('Access-Control-Allow-Headers', '*')
    self.send_header('Access-Control-Allow-Methods', 'POST, GET, OPTIONS')
    self.end_headers()

  # Get message
  def do_GET(self):
    result = []
    qs = {k:v[0] for k,v in urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).items()}
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

  # Send message
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
  httpd = MultiThreadedServer(('',PORT), RequestHandler)
  httpd.serve_forever()

if __name__ == '__main__':
  main()
