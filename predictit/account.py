import atexit
import datetime as dt
import threading
from decimal import Decimal

import requests

from .utils import concurrent_get


class Account(object):
    """Interact with a PredictIt account

    This class handles account-level transactions with PredictIt,
    including authentication and checking balances and market
    participation.  Initializing this object will call `login` and
    `update_all` methods, contacting PredictIt three times.

    Parameters
    ----------
    username : str
        The username for the account that this instance will use
    password : str
        The password for the account that this instance will use
    auth_refresh_interval : None or int, optional (default None)
        If this is set, then a background thread will run `refresh_auth`
        on this interval, measured in seconds.  If this is not set, then
        the auth token will not automatically refresh.

    Attributes
    ----------
    session : requests.Session
        The requests session that executes all transactions with
        PredictIt
    """

    def __init__(self, username, password, auth_refresh_interval=None):
        self.login(username, password)
        self.update_all()
        if auth_refresh_interval is not None:
            self._auth_timer = threading.Timer(
                auth_refresh_interval,
                self.refresh_auth
            )
            self._auth_timer.start()
            atexit.register(self._auth_timer.cancel)
        else:
            self._auth_timer = None

    def __repr__(self):
        return "Account(username={}, auth_expires_in={})".format(
            self._username, self.auth_expires_in
        )

    def login(self, username, password):
        """Login to PredictIt

        Parameters
        ----------
        username : str
            The username for the account that this instance will use
        password : str
            The password for the account that this instance will use
        """
        url = "https://www.predictit.org/api/Account/token"
        self._username = username
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Host": "www.predictit.org",
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 6.1; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/69.0.3497.100 Safari/537.36"
                ),
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "en-US,en;q=0.5",
                "Accept-Encoding": "gzip, deflate, br",
                "Referer": "https://www.predictit.org/dashboard/",
                "DNT": "1",
                "Connection": "keep-alive",
            }
        )
        data = {
            "email": username,
            "password": password,
            "grant_type": "password",
            "rememberMe": "false",
        }
        resp = self.session.post(url, data=data)
        resp.raise_for_status()
        return self._update_token(resp)

    @property
    def username(self):
        """str : Username of the most recently logged-in account"""
        return self._username

    def refresh_auth(self):
        """Refresh PredictIt authentication token"""
        url = "https://www.predictit.org/api/Account/token"
        data = {
            "grant_type": "refresh_token",
            "refresh_token": self._token["refresh_token"],
        }
        resp = self.session.post(url, data=data)
        resp.raise_for_status()
        if threading.current_thread() is self._auth_timer:
            atexit.unregister(self._auth_timer.cancel)
            self._auth_timer = threading.Timer(
                self._auth_timer.interval, self.refresh_auth
            )
            self._auth_timer.start()
            atexit.register(self._auth_timer.cancel)
        return self._update_token(resp)

    def _update_token(self, resp):
        self._token = resp.json(parse_float=Decimal)
        self._token_expires = dt.datetime.strptime(
            self._token[".expires"], "%Y-%m-%dT%H:%M:%S.%f0+00:00"
        )
        self.session.headers.update(
            {"Authorization": "Bearer {}".format(self._token["access_token"])}
        )

        return resp

    @property
    def auth_expires_in(self):
        """int: Seconds until authentication token expires"""
        expires_in = self._token_expires - dt.datetime.utcnow()
        self._token["expires_in"] = int(expires_in.total_seconds()) - 1
        return self._token["expires_in"]

    def update_balances(self):
        """Update cash_balance and investment_balance properties

        Requests https://www.predictit.org/api/User/Wallet/Balance to
        update properties cash_balance and investment_balance.

        Returns
        -------
        requests.Response
            The response from requesting balances from PredictIt
        """
        url = "https://www.predictit.org/api/User/Wallet/Balance"
        resp = self.session.get(url, timeout=5)
        self._update_balances(resp)

        return resp

    def _update_balances(self, resp):
        resp.raise_for_status()

        balances = resp.json(parse_float=Decimal)
        self._cash_balance = Decimal(balances["accountBalanceDecimal"])
        self._investment_balance = Decimal(balances["portfolioBalanceDecimal"])

        return resp

    @property
    def cash_balance(self):
        """decimal.Decimal: Cash available to invest"""
        return self._cash_balance

    @property
    def investment_balance(self):
        """decimal.Decimal: Total dollars spent on currently owned shares"""
        return self._investment_balance

    def update_contracts(self):
        """Update properties related to currently owned shares

        Requests https://www.predictit.org/api/Profile/Shares to update
        properties: `my_market_ids`, `my_contract_ids`,
        `is_trading_suspended`, and `is_trading_suspended_message`.

        Returns
        -------
        requests.Response
            The response from requesting currently owned shares from
            PredictIt
        """
        url = "https://www.predictit.org/api/Profile/Shares"
        data = {"sort": "traded", "sortParameter": "ALL"}
        resp = self.session.get(url, data=data, timeout=5)
        self._update_contracts(resp)
        return resp

    def _update_contracts(self, resp):
        resp.raise_for_status()

        contracts_dict = resp.json(parse_float=Decimal)
        self._is_trading_suspended = contracts_dict["isTradingSuspended"]
        self._is_trading_suspended_message = contracts_dict["isTradingSuspendedMessage"]
        self._my_market_ids = []
        self._my_contract_ids = []
        if contracts_dict["markets"] is not None:
            for mkt in contracts_dict["markets"]:
                self._my_market_ids.append(mkt["marketId"])
                for c in mkt["marketContracts"]:
                    self._my_contract_ids.append(c["contractId"])

        return resp

    @property
    def is_trading_suspended(self):
        """bool"""
        return self._is_trading_suspended

    @property
    def is_trading_suspended_message(self):
        """NoneType (or string?)"""
        return self._is_trading_suspended_message

    @property
    def my_contract_ids(self):
        """list of int: IDs of contracts with currently owned shares"""
        return self._my_contract_ids.copy()

    @property
    def my_market_ids(self):
        """list of int: IDs of markets with currently owned shares"""
        return self._my_market_ids.copy()

    def update_all(self):
        """Concurrently run update_balances() and update_contracts()

        Returns
        -------
        list of requests.Response
            In order, responses from requesting balances and from
            requesting currently owned shares
        """
        urls = [
            "https://www.predictit.org/api/User/Wallet/Balance",
            "https://www.predictit.org/api/Profile/Shares",
        ]
        responses = concurrent_get(urls, session=self.session)
        self._update_balances(responses[0])
        self._update_contracts(responses[1])
        return responses

    def search_markets(self, query, page=1, items_per_page=30):
        """Search active markets for given query

        Parameters
        ----------
        query : str
            Query to search in markets
        page : int, optional (default=1)
            Index for which page of results to return (1-based)
        items_per_page : int, optional (default=30)
            Items per page of results.  If there are more results than
            items per page, then they will continue on the next page,
            which can be requested

        Returns
        -------
        requests.Response
        """
        url = "https://www.predictit.org/api/Browse/Search/{}".format(query)
        params = (("page", page), ("itemsPerPage", items_per_page))
        resp = self.session.get(url, params=params, timeout=5)
        resp.raise_for_status()
        return resp
