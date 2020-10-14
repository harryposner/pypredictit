import datetime as dt
from decimal import Decimal

import pytz

from .utils import concurrent_get


class Market(object):
    """Interact with PredictIt markets

    This class handles market-level transactions with PredictIt,
    including getting market risk, payouts, and contract IDs.
    Initializing this object will call the `update_all` method,
    contacting PredictIt twice.

    Parameters
    ----------
    account : predictit.Account
    market_id : int
    """

    def __init__(self, account, market_id):
        if not isinstance(market_id, int):
            raise TypeError("Market ID must be int, not {}".format(type(market_id)))
        else:
            self._market_id = market_id
        self.account = account
        self.update_all()

    def __repr__(self):
        repr_fmt = "Market(market_id={}, market_name={})"
        return repr_fmt.format(self.market_id, self.market_name)

    @property
    def market_id(self):
        """int"""
        return self._market_id

    def update_info(self):
        """Update market properties other than contract IDs

        Requests http://www.predictit.org/api/Market/{self.market_id} to
        update properties:
            `market_name`
            `market_type`
            `end_date`
            `is_active`
            `rule`
            `have_ownership`
            `have_trade_history`
            `investment`
            `max_payout`
            `info`
            `date_opened`
            `is_market_watched`
            `status`
            `is_open`
            `is_open_status_message`
            `is_trading_suspended`
            `is_trading_suspended_message`
            `is_engine_busy`
            `is_engine_busy_message`

        Returns
        -------
        requests.Response
            The response from requesting market info from PredictIt
        """
        url_fmt = "https://www.predictit.org/api/Market/{s.market_id}"
        resp = self.account.session.get(url_fmt.format(s=self), timeout=5)
        self._update_info(resp)
        return resp

    def _update_info(self, resp):
        resp.raise_for_status()

        mkt_info = resp.json(parse_float=Decimal)

        self._market_name = mkt_info["marketName"]
        self._market_type = mkt_info["marketType"]
        if mkt_info["dateEndString"] == "N/A":
            self._end_date = None
        else:
            end_date = dt.datetime.strptime(
                mkt_info["dateEndString"][:19], "%m/%d/%Y %I:%M %p"
            )
            tz_string = mkt_info["dateEndString"][19:].strip(" ()")
            if tz_string == "ET":
                # Declare naive datetime as US East, then convert to UTC
                self._end_date = (
                    end_date.astimezone(pytz.timezone("US/Eastern"))
                    .astimezone(pytz.timezone("UTC"))
                    .replace(tzinfo=None)
                )
            else:
                # Why, oh why, doesn't PredictIt use a standard timezone
                # format?
                raise NotImplementedError(
                    'PredictIt returned a timezone other than "ET" (should '
                    "not happen)"
                )
        self._is_active = mkt_info["isActive"]
        self._rule = mkt_info["rule"]
        self._have_ownership = mkt_info["userHasOwnership"]
        self._have_trade_history = mkt_info["userHasTradeHistory"]
        self._investment = mkt_info["userInvestment"]
        self._max_payout = mkt_info["userMaxPayout"]
        self._info = mkt_info["info"]
        self._date_opened = dt.datetime.strptime(
            mkt_info["dateOpened"], "%Y-%m-%dT%H:%M:%S.%f"
        )
        self._is_market_watched = mkt_info["isMarketWatched"]
        self._status = mkt_info["status"]
        self._is_open = mkt_info["isOpen"]
        self._is_open_status_message = mkt_info["isOpenStatusMessage"]
        self._is_trading_suspended = mkt_info["isTradingSuspended"]
        self._is_trading_suspended_message = mkt_info["isTradingSuspendedMessage"]

        self._is_engine_busy = mkt_info["isEngineBusy"]
        self._is_engine_busy_message = mkt_info["isEngineBusyMessage"]

        return resp

    @property
    def market_name(self):
        """str : Human-readable name for this market"""
        return self._market_name

    @property
    def market_type(self):
        """int : I'm not sure what this is.  These are my best guesses:

            0 : Single-contract market
            3 : Multiple-contract linked market
        """
        return self._market_type

    @property
    def end_date(self):
        """NoneType or datetime.datetime : Date by which market closes

        If the market has a definite end date, then this returns the UTC
        naive datetime by which the market should close.  The market may
        close before the end date if the conditions for resolving the
        market are met (e.g.  "Will X run?" if X announces candidacy).
        If there is no definite end date, this returns None.
        """
        return self._end_date

    @property
    def is_active(self):
        """bool : True if the market has not yet been settled, else False."""
        return self._is_active

    @property
    def rule(self):
        """str : Human-readable rule for resolving this market"""
        return self._rule

    @property
    def have_ownership(self):
        """bool : True if user owns any shares in this market"""
        return self._have_ownership

    @property
    def have_trade_history(self):
        """bool : True if user has traded any shares in this market"""
        return self._have_trade_history

    @property
    def investment(self):
        """decimal.Decimal : Dollars spent to buy currently owned shares"""
        return self._investment

    @property
    def max_payout(self):
        """decimal.Decimal : Maximum dollar payout in market net of fees"""
        return self._max_payout

    @property
    def info(self):
        return self._info

    @property
    def date_opened(self):
        """datetime.datetime : UTC naive datetime when market opened"""
        return self._date_opened

    @property
    def is_market_watched(self):
        """bool : True if user is watching market on profile"""
        return self._is_market_watched

    @property
    def status(self):
        """str : 'Open' or 'Expired', but can't rule out other values"""
        return self._status

    @property
    def is_open(self):
        """bool"""
        return self._is_open

    @property
    def is_open_status_message(self):
        return self._is_open_status_message

    @property
    def is_trading_suspended(self):
        """bool"""
        return self._is_trading_suspended

    @property
    def is_trading_suspended_message(self):
        return self._is_trading_suspended_message

    @property
    def is_engine_busy(self):
        """bool"""
        return self._is_engine_busy

    @property
    def is_engine_busy_message(self):
        return self._is_engine_busy_message

    def update_contracts(self):
        """Get the contract IDs for this market

        Requests https://www.predictit.org/api/Market/{self.market_id}/Contracts
        to update the `contract_ids` property.

        Returns
        -------
        requests.Response
            The response from requesting the contracts for this market
            from PredictIt
        """
        url_fmt = "https://www.predictit.org/api/Market/{s.market_id}/Contracts"
        resp = self.account.session.get(url_fmt.format(s=self), timeout=5)
        self._update_contracts(resp)
        return resp

    def _update_contracts(self, resp):
        resp.raise_for_status()

        contracts = resp.json(parse_float=Decimal)

        # We don't want to make a list of actual Contract objects since
        # that would make three requests for every contract in the
        # market, and we want to be explicit whenever we make a request.
        self._contract_ids = [c["contractId"] for c in contracts]

        return resp

    @property
    def contract_ids(self):
        """list of int : The IDs for each contract in this market"""
        # We don't want to return the original, since lists are mutable
        return self._contract_ids.copy()

    def update_all(self):
        """Concurrently run `update_info` and `update_contracts`

        Returns
        -------
        list of requests.Response
            In order, responses from requesting market info and from
            requesting contracts for this market
        """
        url_fmts = [
            "https://www.predictit.org/api/Market/{s.market_id}",
            "https://www.predictit.org/api/Market/{s.market_id}/Contracts",
        ]
        urls = [fmt.format(s=self) for fmt in url_fmts]
        responses = concurrent_get(urls, session=self.account.session)
        self._update_info(responses[0])
        self._update_contracts(responses[1])
        return responses
