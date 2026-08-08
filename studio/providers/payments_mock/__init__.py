"""Mock payments provider — NEVER real money.

Refunds go to this mock provider. Do not add a Stripe/PayPal/Adyen key
to this repo in any mode. A live test-mode key on a real account is still
a real account.
"""

from studio.providers.payments_mock.provider import MockPaymentsProvider

__all__ = ["MockPaymentsProvider"]
