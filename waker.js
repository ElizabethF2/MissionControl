// Deploy as a gscript webapp
// Enables a client to "wake" a server and have it start polling a message bus
// The server should stop polling the bus if it doesn't receive any messages after a timeout
// This reduces the uptime of the bus to avoid uptime limits on free hosting plans

var CACHE = CacheService.getScriptCache();
var LOCK = LockService.getScriptLock();

var MAX_SLEEP_MS = 4.5*60*1000;
var POLL_IVL_MS = 800;
var LOCK_TIMEOUT_MS = 30000;
var EVENT_NAME = 'WAKER_EVENT';

function signal_event()
{
  CACHE.put(EVENT_NAME, '1');
}

function wait_for_event()
{
  var iter_count = Math.floor(MAX_SLEEP_MS/POLL_IVL_MS);
  for (var i=0; i<iter_count; ++i)
  {
    if (CACHE.get(EVENT_NAME))
    {
      LOCK.waitLock(LOCK_TIMEOUT_MS);
      if (CACHE.get(EVENT_NAME))
      {
        CACHE.remove(EVENT_NAME);
        return true;
      }
      LOCK.releaseLock();
    }
    Utilities.sleep(POLL_IVL_MS);
  }
  return false;
}

function doGet(e)
{
  var result = null;

  if (e.parameter.wait)
  {
    result = wait_for_event();
  }
  else if (e.parameter.signal)
  {
    signal_event();
    result = true;
  }

  var js = JSON.stringify(result);
  return ContentService.createTextOutput(js).setMimeType(ContentService.MimeType.JSON);
}
