"""Hit the real BookingOfferListCreateView through DRF to verify ?status=."""
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.accounts.models import User
from apps.bookings.views import BookingOfferListCreateView

buyer_b = User.objects.get(email="buyer.b@demo.getavails")
factory = APIRequestFactory()
view = BookingOfferListCreateView.as_view()


def call(query):
    req = factory.get(f"/api/v1/bookings/offers/{query}")
    force_authenticate(req, user=buyer_b)
    resp = view(req)
    resp.render()
    return resp


for query in [
    "?scope=received&status=pending",
    "?scope=received&status=confirmed",
    "?scope=received&status=past",
    "?scope=received",            # no status -> all received
    "?scope=received&status=foo", # invalid status
    "",                           # default scope=received, no status
]:
    resp = call(query)
    data = resp.data
    if not data.get("success", True) is False and "results" in data:
        titles = [(r["title"], r["status"]) for r in data.get("results", [])]
        print(f"\nGET {query or '(none)'}  -> HTTP {resp.status_code}  count={data.get('count')}")
        for t, s in titles:
            print(f"    {s:<9} {t}")
    else:
        err = data.get("error", {})
        print(f"\nGET {query or '(none)'}  -> HTTP {resp.status_code}  "
              f"code={err.get('code')!r}  message={err.get('message')!r}")
