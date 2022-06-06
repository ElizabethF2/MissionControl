var MISSIONCONTROL_CLIENT_IS_LOADED = true;
var MISSIONCONTROL_USE_PROXY = (window.MISSIONCONTROL_USE_PROXY === undefined) ? true : window.MISSIONCONTROL_USE_PROXY;

var mc_generate_uid = function()
{
  if (window.crypto)
  {
    if (crypto.randomUUID)
    {
      return crypto.randomUUID();
    }
    var buf = new Uint8Array(27);
    crypto.getRandomValues(buf);
    return btoa(String.fromCharCode.apply(null, buf));
  }
  return (''+Math.random()).slice(2)+(''+Math.random()).slice(2);
};

var MC_CLIENT_ID = 'MissionControl-Client-' + mc_generate_uid();

var mc_call_api = function(URL, content, callback, error_callback)
{
  var method = content ? 'POST' : 'GET';
  var xhr = new XMLHttpRequest();
  xhr.open(method, URL);

  xhr.onreadystatechange = function(){
    if(xhr.readyState == 4)
    {
      callback(JSON.parse(xhr.responseText));
    }
  }
  
  if (error_callback)
  {
    xhr.onerror = error_callback;
  }

  if (content)
  {
    xhr.setRequestHeader('Content-Type', 'application/json;charset=UTF-8');
    xhr.send(JSON.stringify(content));
  }
  else
  {
    xhr.send();
  }
};

var mc_wake_server = function()
{
  mc_call_api(MC_WAKER_URL+'?signal=1', null, function(r){});
}

var mc_check_inbox_loop = function(message_handler)
{
  if (window.MC_INBOX_LOOP_RUNNING)
  {
    console.warn('MissionControl: Inbox loop started multiple times');
  }
  window.MC_INBOX_LOOP_RUNNING = true;

  mc_call_api(MC_MESSAGE_BUS_URL+'?name='+MC_CLIENT_ID, null, function(inbox)
  {
    for (message of inbox)
    {
      message_handler(message);
    }
    window.MC_INBOX_LOOP_RUNNING = false;
    mc_check_inbox_loop(message_handler);
  },
  function()
  {
    // Reset the flag if an error occurs so the loop will be restarted at the next request
    window.MC_INBOX_LOOP_RUNNING = false;
  });
};

var mc_send_message = function(message)
{
  message.recipient = MC_SERVER_NAME;
  message.from = MC_CLIENT_ID;
  mc_call_api(MC_MESSAGE_BUS_URL, message, function(r){});
};

var mc_pending_proxied_requests = {};

var mc_handle_proxy_message = function(message)
{
  if (message.action == 'proxy')
  {
    var xhr = mc_pending_proxied_requests[message.uid];
    xhr.readyState = 4;
    xhr.status = message.status_code;
    xhr.responseText = atob(message.body);
    xhr.headers = message.headers;
    for (name in message.headers)
    {
      if (name == 'Set-Cookie')
      {
        document.cookie = message.headers[name];
      }
    }
    xhr.onreadystatechange();
    delete mc_pending_proxied_requests[message.uid];
    return true;
  }
  return false;
}

class MCXHRProxy
{
  constructor()
  {
    this.readyState = 0;
    this.status = 0;
    this.headers = {};
    this.uid = mc_generate_uid();
  }

  open(method, url)
  {
    this.readyState = 1;
    this.method = method;
    this.url = url;
  };

  setRequestHeader(name, value)
  {
    this.headers[name] = value;
  }

  send(body)
  {
    if (this.headers['User-Agent'] === undefined)
    {
      this.headers['User-Agent'] = navigator.userAgent;
    }
    if (this.headers['Cookie'] === undefined && document.cookie)
    {
      this.headers['Cookie'] = document.cookie;
    }
    if (this.headers['Content-Length'] === undefined)
    {
      this.headers['Content-Length'] = (body === undefined) ? 0 : body.length;
    }

    if (window.MC_EXTENSION_NAME !== undefined)
    {
      this.url = '/' + MC_EXTENSION_NAME + (new URL(this.url, 'http://x')).href.slice(8);
    }
    
    var headers = [];
    for (name in this.headers)
    {
      headers.push(name + ': ' + this.headers[name]);
    }
    headers = headers.join('\r\n');

    var message = {
      'action': 'proxy',
      'uid': this.uid,
      'url': this.url,
      'method': this.method,
      'headers': headers
    };

    if (body !== undefined)
    {
      message.body = body;
    }

    if (!window.MC_INBOX_LOOP_RUNNING)
    {
      mc_wake_server();
      mc_check_inbox_loop(mc_handle_proxy_message);
    }

    mc_pending_proxied_requests[this.uid] = this;

    mc_send_message(message);
  }
}
