import os
from concurrent.futures import ThreadPoolExecutor

import requests


def concurrent_get(urls, session=None, max_workers=5, timeout=5):
    """Concurrently request a list of URLs

    Parameters
    ----------
    urls : iterable of str
        The URLs to request
    session : requests.Session, optional
        The session with which to request the URLs (uses no session if
        omitted)
    max_workers : int, optional (default=5)
        The maximum number of threads with which to make requests
    timeout : int, optional (default=5)
        Timeout in seconds for requests and for thread execution

    Returns
    -------
    list of requests.Response
        Responses from requesting URLs, in order given by `urls`
        parameter
    """
    if session is None:
        get = requests.get
    else:
        get = session.get
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [pool.submit(get, url, timeout=timeout) for url in urls]
        return [f.result(timeout=timeout) for f in futures]


def notify_ifttt(message, title=None, link=None, key=None):
    """Send notification via IFTTT

    Parameters
    ----------
    message : str
    title : str, optional
    link : str, optional
    key : str, optional
        API key for IFTTT.  If not set, imports the environmental
        variable IFTTT_WEBHOOK_KEY.

    Returns
    -------
    requests.Response
    """
    url_fmt = "https://maker.ifttt.com/trigger/predictit_trade/with/key/{}"
    if key is None:
        key = os.environ["IFTTT_WEBHOOK_KEY"]
    if message is None or len(message) == 0:
        # message can be False, so we can't just test "if message"
        raise ValueError("IFTTT message cannot be empty string or None")
    data = {"value1": title, "value2": message, "value3": link}
    return requests.post(url_fmt.format(key), data=data)
