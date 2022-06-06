// Message Bus with long polling
// Deploy as a gscript webapp
// Frequently drops messages due to gscript's high cache-miss rate
// Use not recommended

var CACHE = CacheService.getScriptCache();
var LOCK = LockService.getScriptLock();

var MAX_SLEEP_MS = 300000;
var POLL_IVL_MS = 800;
var LOCK_TIMEOUT_MS = 30000;

// If message is non-null add it to name's inbox else get name's mailbox and clear it
// Caller is responsible for validating name and message
// Returns name's inbox if message is null else returns null
function add_or_get_messages(name, message)
{
  var result = null;

  LOCK.waitLock(LOCK_TIMEOUT_MS);

  var inboxes = JSON.parse(CACHE.get('INBOXES'));
  if (inboxes == null)
  {
    inboxes = {};
  }

  var inbox = inboxes[name];
  if (inbox === undefined)
  {
    inbox = [];
  }

  if (message === null)
  {
    // Get messages
    result = inbox;
    delete inboxes[name];
  }
  else
  {
    // Add message
    inbox.push(message);
    inboxes[name] = inbox;
  }

  CACHE.put('INBOXES', JSON.stringify(inboxes));
  
  LOCK.releaseLock();
  
  return result;
}

function signal_event(name)
{
  var event_name = 'EVT_'+name;
  CACHE.put(event_name, '1');
}

function wait_for_event(name)
{
  var event_name = 'EVT_'+name;
  var iter_count = Math.floor(MAX_SLEEP_MS/POLL_IVL_MS);
  for (var i=0; i<iter_count; ++i)
  {
    if (CACHE.get(event_name))
    {
      LOCK.waitLock(LOCK_TIMEOUT_MS);
      if (CACHE.get(event_name))
      {
        CACHE.remove(event_name);
        return true;
      }
      LOCK.releaseLock();
    }
    Utilities.sleep(POLL_IVL_MS);
  }
  return false;
}

function validate_and_send_message(message)
{
  if ((typeof message) != 'object')
  {
    throw 'Invalid message type';
  }
  if ((typeof message.recipient) != 'string')
  {
    throw 'Invalid message recipient';
  }
  var recipient = message.recipient;
  delete message.recipient;

  add_or_get_messages(recipient, message);
  signal_event(recipient);
  return ContentService.createTextOutput('true').setMimeType(ContentService.MimeType.JSON);
}

// Check for messages
function doGet(e)
{
  var name = e.parameter.name;
  if (name)
  {
    if ((typeof name) != 'string')
    {
      throw 'Invalid inbox name';
    }

    wait_for_event(name);

    var inbox = add_or_get_messages(name, null);
    var js = JSON.stringify(inbox);
    return ContentService.createTextOutput(js).setMimeType(ContentService.MimeType.JSON);
  }
  else
  {
    // Since we can't handle OPTIONS, need to also handle sending messages via GET to workaround CORS
    var message = JSON.parse(e.parameter.message);
    return validate_and_send_message(message);
  }
}

// Send a message
function doPost(e)
{
  var message = JSON.parse(e.postData.contents);
  return validate_and_send_message(message);
}
