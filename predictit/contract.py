import datetime as dt
from collections import namedtuple
from decimal import Decimal

from .utils import concurrent_get


class Contract(object):
    """Interact with PredictIt contracts

    This class handles contract-level transactions with PredictIt,
    including trading and viewing order books and currently owned
    shares.  Initializing this object will call the `update_all` method,
    contacting PredictIt four times.

    Parameters
    ----------
    account : predictit.Account
    contract_id : int
    """

    def __init__(self, account, contract_id):

        if not isinstance(contract_id, int):
            raise TypeError("Contract ID must be int, not {}".format(type(contract_id)))
        else:
            self._contract_id = contract_id
        self.account = account
        self.update_all()

    def __repr__(self):
        repr_fmt = "Contract(contract_id={}, contract_name={})"
        return repr_fmt.format(self.contract_id, self.contract_name)

    @property
    def contract_id(self):
        """int"""
        return self._contract_id

    def _post_order(self, trade_type, price, quantity):
        # Trade types
        # 0 = Buy no
        # 1 = Buy yes
        # 2 = Sell no
        # 3 = Sell yes
        int_price = int(100 * price)
        if not 1 <= int_price <= 99:
            raise ValueError("Price must be between $0.01 and $0.99")
        if not isinstance(quantity, int):
            raise TypeError("Quantity must be an int, not {}".format(type(quantity)))
        if quantity <= 0:
            raise ValueError("Quantity must be positive, not {}".format(quantity))

        if self.my_prediction is not None:
            if self.my_prediction and trade_type in (0, 2):
                raise ValueError("Can't trade No shares and own Yes shares")
            elif not self.my_prediction and trade_type in (1, 3):
                raise ValueError("Can't trade Yes shares and own No shares")

        if quantity > self.shares_owned and trade_type in (2, 3):
            raise ValueError(
                "Can't sell {} shares; only own {}".format(quantity, self.shares_owned)
            )

        if trade_type in (0, 1):
            # TODO: raise error if market risk would exceed cash balance
            if price * quantity + self.investment > 850:
                raise ValueError("Cannot invest more than $850 in a contract")

        url = "https://www.predictit.org/api/Trade/SubmitTrade"
        data = {
            "pricePerShare": str(int_price),
            "quantity": str(quantity),
            "contractId": str(self.contract_id),
            "tradeType": str(trade_type),
        }
        resp = self.account.session.post(url, data=data)
        resp.raise_for_status()

        return resp

    def buy_no(self, price, quantity):
        """Place an order to buy No shares in this contract

        Posts to https://www.predictit.org/api/Trade/SubmitTrade to
        place an order to buy `quantity` No shares at `price` dollars
        per share.  Checks `self.api.cash_balance` to confirm that user
        has enough cash-on-hand to post the order and checks
        `self.my_prediction` to confirm that user doesn't own Yes
        shares.

        Parameters
        ----------
        price : numeric between zero and one, exclusive
            The price per share
        quantity : int greater than zero
            The number of No shares to buy

        Returns
        -------
        requests.Response
        """
        return self._post_order("0", price, quantity)

    def buy_yes(self, price, quantity):
        """Place an order to buy Yes shares in this contract

        Posts to https://www.predictit.org/api/Trade/SubmitTrade to
        place an order to buy `quantity` Yes shares at `price` dollars
        per share.  Checks `self.api.cash_balance` to confirm that user
        has enough cash-on-hand to post the order and checks
        `self.my_prediction` to confirm that user doesn't own No shares.

        Parameters
        ----------
        price : numeric between zero and one, exclusive
            The price per share
        quantity : int greater than zero
            The number of Yes shares to buy

        Returns
        -------
        requests.Response
        """
        return self._post_order("1", price, quantity)

    def sell_no(self, price, quantity):
        """Place an order to sell No shares in this contract

        Posts to https://www.predictit.org/api/Trade/SubmitTrade to
        place an order to sell `quantity` No shares at `price` dollars
        per share.  Checks `self.shares_owned` to confirm that user owns
        at least `quantity` shares and checks `self.my_prediction` to
        confirm that user doesn't own Yes shares.

        Parameters
        ----------
        price : numeric between zero and one, exclusive
            The price per share
        quantity : int greater than zero
            The number of No shares to sell

        Returns
        -------
        requests.Response
        """
        return self._post_order("2", price, quantity)

    def sell_yes(self, price, quantity):
        """Place an order to sell Yes shares in this contract

        Posts to https://www.predictit.org/api/Trade/SubmitTrade to
        place an order to sell `quantity` No shares at `price` dollars
        per share.  Checks `self.shares_owned` to confirm that user owns
        at least `quantity` shares and checks `self.my_prediction` to
        confirm that user doesn't own No shares.

        Parameters
        ----------
        price : numeric between zero and one, exclusive
            The price per share
        quantity : int greater than zero
            The number of Yes shares to sell

        Returns
        -------
        requests.Response
        """
        return self._post_order("3", price, quantity)

    def update_order_book(self):
        """Update the order book for this contract

        Requests https://www.predictit.org/api/Trade/{self.contract_id}/OrderBook
        to update the `no_asks`, `yes_asks`, `no_bids`, and `yes_bids`
        properties.

        Returns
        -------
        requests.Response
            The response from requesting the order book for this
            contract from PredictIt
        """
        url_fmt = "https://www.predictit.org/api/Trade/{s.contract_id}/OrderBook"
        resp = self.account.session.get(url_fmt.format(s=self), timeout=5)
        self._update_order_book(resp)
        return resp

    def _update_order_book(self, resp):
        resp.raise_for_status()

        orders = resp.json(parse_float=Decimal)

        self._order_book = {}
        self._order_book[1] = [
            (n["pricePerShare"], n["quantity"]) for n in orders["yesOrders"]
        ]
        self._order_book[0] = [
            (n["pricePerShare"], n["quantity"]) for n in orders["noOrders"]
        ]

        # PredictIt sends us the order book already sorted, but we can't
        # rely on that, and getting the best available order is useful
        # enough that I don't want to need boilerplate every time I get
        # it.
        self._order_book[1].sort()
        self._order_book[0].sort()
        return resp

    @property
    def no_asks(self):
        """list of (decimal.Decimal, int) tuples : Open No asks on order book

        List of (price, quantity) tuples sorted from best price to
        worst.  These tuples can be unpacked and passed to the `buy_no`
        method.
        """
        return [(1 - p, q) for p, q in self._order_book[0]]

    @property
    def yes_asks(self):
        """list of (decimal.Decimal, int) tuples : Open Yes asks on order book

        List of (price, quantity) tuples sorted from best price to
        worst.  These tuples can be unpacked and passed to the `buy_yes`
        method.
        """
        return self._order_book[1].copy()

    @property
    def no_bids(self):
        """list of (decimal.Decimal, int) tuples : Open No bids on order book

        List of (price, quantity) tuples sorted from best price to
        worst.  These tuples can be unpacked and passed to the `sell_no`
        method.
        """
        return [(1 - p, q) for p, q in self._order_book[1]]

    @property
    def yes_bids(self):
        """list of (decimal.Decimal, int) tuples : Open Yes bids on order book

        List of (price, quantity) tuples sorted from best price to
        worst.  These tuples can be unpacked and passed to the
        `sell_yes` method.
        """
        return self._order_book[0].copy()

    def update_shares(self):
        """Update user's currently owned shares for this contract

        Requests https://www.predictit.org/api/Profile/contract/{self.contract_id}/Shares
        to update the `my_prediction`, `shares_owned`, `investment`, and
        `mean_price_per_share` properties.

        Returns
        -------
        requests.Response
            The response from requesting the currently owned shares for
            this contract from PredictIt
        """
        url_fmt = (
            "https://www.predictit.org/api/Profile/contract/{s.contract_id}/Shares"
        )
        resp = self.account.session.get(url_fmt.format(s=self), timeout=5)
        self._update_shares(resp)
        return resp

    def _update_shares(self, resp):
        resp.raise_for_status()
        shares_info = resp.json(parse_float=Decimal)
        self._contract_name = shares_info["contractName"]
        shares = shares_info["shares"]

        if not shares:
            self._my_prediction = None
        else:
            self._my_prediction = shares[0]["predictionType"]

        self._shares_owned = self._investment = 0
        for share in shares:
            if '.' in share["dateExecuted"]:
                str_format = "%Y-%m-%dT%H:%M:%S.%f"
            else:
                str_format = "%Y-%m-%dT%H:%M:%S"
            share["dateExecuted"] = dt.datetime.strptime(
                share["dateExecuted"], str_format
            )
            self._shares_owned += share["sharesOwned"]
            self._investment += share["pricePerShare"] * share["sharesOwned"]

        self.share_details = shares
        return resp

    @property
    def contract_name(self):
        """str"""
        return self._contract_name

    @property
    def my_prediction(self):
        """NoneType or int (0 or 1) : 0 or 1 if user owns shares, else None

        If the user does not own any shares, then `my_prediction` is
        None.  Otherwise, it corresponds to the type of share the user
        owns (0 for No, 1 for Yes).  Remember, you can't simultaneously
        own No and Yes shares.
        """
        return self._my_prediction

    @property
    def shares_owned(self):
        """int : The number of shares the user owns in this contract"""
        return self._shares_owned

    @property
    def investment(self):
        """decimal.Decimal : Dollars user spent to buy currently owned shares"""
        return self._investment

    @property
    def mean_price_per_share(self):
        """decimal.Decimal"""
        return self.investment / self.shares_owned

    def update_my_orders(self):
        """Update user's currently owned shares for this contract

        Requests https://www.predictit.org/api/Profile/contract/{self.contract_id}/Offers
        to update the `have_open_orders`, `my_no_bids`,`my_yes_bids`,
        `my_no_asks`, and `my_yes_asks` properties.

        Returns
        -------
        requests.Response
            The response from requesting the currently owned shares for this
            contract from PredictIt
        """
        url_fmt = (
            "https://www.predictit.org/api/Profile/contract/{s.contract_id}/Offers"
        )
        resp = self.account.session.get(url_fmt.format(s=self), timeout=5)
        self._update_my_orders(resp)
        return resp

    def _update_my_orders(self, resp):
        resp.raise_for_status()
        my_orders = resp.json(parse_float=Decimal)
        field_names = [
            "order_id",
            "contract_id",
            "price",
            "original_quantity",
            "remaining_quantity",
            "date_created",
            "is_processed",
        ]
        OwnOrder = namedtuple("OwnOrder", field_names)
        self._my_orders = {k: [] for k in range(4)}
        for raw_order in my_orders["offers"]:
            order_date = dt.datetime.strptime(
                raw_order["dateCreated"], "%Y-%m-%dT%H:%M:%S.%f"
            )
            order = OwnOrder(
                order_id=raw_order["offerId"],
                contract_id=raw_order["contractId"],
                price=raw_order["pricePerShare"],
                original_quantity=raw_order["quantity"],
                remaining_quantity=raw_order["remainingQuantity"],
                date_created=order_date,
                is_processed=raw_order["isProcessed"],
            )

            self._my_orders[raw_order["tradeType"]].append(order)
        return resp

    @property
    def have_open_orders(self):
        """bool : True if user has any open orders in this contract"""
        return any(self._my_orders.values())

    @property
    def my_no_bids(self):
        """list of OwnOrder namedtuples

        OwnOrder namedtuples have the following fields, in order:
            order_id : int
            contract_id : int
            price : decimal.Decimal
            original_quantity : int
            remaining_quantity : int
            date_created : int
            is_processed : bool
        """
        return self._my_orders[0].copy()

    @property
    def my_yes_bids(self):
        """list of OwnOrder namedtuples

        OwnOrder namedtuples have the following fields, in order:
            order_id : int
            contract_id : int
            price : decimal.Decimal
            original_quantity : int
            remaining_quantity : int
            date_created : int
            is_processed : bool
        """
        return self._my_orders[1].copy()

    @property
    def my_no_asks(self):
        """list of OwnOrder namedtuples

        OwnOrder namedtuples have the following fields, in order:
            order_id : int
            contract_id : int
            price : decimal.Decimal
            original_quantity : int
            remaining_quantity : int
            date_created : int
            is_processed : bool
        """
        return self._my_orders[2].copy()

    @property
    def my_yes_asks(self):
        """list of OwnOrder namedtuples

        OwnOrder namedtuples have the following fields, in order:
            order_id : int
            contract_id : int
            price : decimal.Decimal
            original_quantity : int
            remaining_quantity : int
            date_created : int
            is_processed : bool
        """
        return self._my_orders[3].copy()

    def cancel_order(self, order_id):
        """Cancel an outstanding order on this contract

        Posts to https://www.predictit.org/api/Trade/CancelOffer/{order_id} to
        cancel the order identified by `order_id`.

        Parameters
        ----------
        order_id : int
            The ID for the order to cancel

        Returns
        -------
        requests.Response
        """
        url_fmt = "https://www.predictit.org/api/Trade/CancelOffer/{}"
        url = url_fmt.format(order_id)
        resp = self.account.session.post(url)
        resp.raise_for_status()
        return resp

    def cancel_all_orders(self):
        """Cancel all outstanding order on this contract

        Posts to https://www.predictit.org/api/Trade/CancelAllOffers/{self.contract_id}
        to cancel all outstanding orders for this contract.

        Returns
        -------
        requests.Response
        """
        url_fmt = "https://www.predictit.org/api/Trade/CancelAllOffers/{s.contract_id}"
        url = url_fmt.format(s=self)
        resp = self.account.session.post(url)
        resp.raise_for_status()
        return resp

    def update_all(self):
        """Concurrently update internal state

        Sends four requests to PredictIt to update order book, currently
        owned shares, outstanding orders, and the market ID.

        Returns
        -------
        list of requests.Response
            In order, responses from requesting the order book, current
            owned shares, outstanding orders, and the market ID.
        """
        url_fmts = [
            "https://www.predictit.org/api/Trade/{s.contract_id}/OrderBook",
            "https://www.predictit.org/api/Profile/contract/{s.contract_id}/Shares",
            "https://www.predictit.org/api/Profile/contract/{s.contract_id}/Offers",
        ]
        urls = [fmt.format(s=self) for fmt in url_fmts]
        responses = concurrent_get(urls, session=self.account.session)
        self._update_order_book(responses[0])
        self._update_shares(responses[1])
        self._update_my_orders(responses[2])
        return responses
