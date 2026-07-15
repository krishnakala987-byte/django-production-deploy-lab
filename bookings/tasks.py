# bookings/tasks.py

import csv
import datetime

from celery import shared_task
from django.core.mail import send_mail
from django.db.models import Count, Sum

from .models import Booking


@shared_task(
    autoretry_for=(ConnectionError,),
    retry_backoff=True,
    max_retries=5,
)
def send_booking_email(booking_id):
    b = Booking.objects.get(id=booking_id)

    send_mail(
        subject=f"Booking #{b.id} {b.status}",
        message=f"Hi {b.user.username}, your booking for {b.trip.title} is {b.status}.",
        from_email="noreply@rochalab.in",
        recipient_list=[f"{b.user.username}@example.com"],
    )

    return f"Emailed booking {booking_id}"


@shared_task
def nightly_report():
    path = f"/srv/myapp/report_{datetime.date.today()}.csv"

    with open(path, "w", newline="") as f:
        writer = csv.writer(f)

        writer.writerow(["Trip", "Confirmed Bookings", "Revenue"])

        rows = (
            Booking.objects.filter(status="confirmed")
            .values("trip__title")
            .annotate(
                n=Count("id"),
                rev=Sum("amount"),
            )
        )

        for row in rows:
            writer.writerow(
                [
                    row["trip__title"],
                    row["n"],
                    row["rev"],
                ]
            )

    return path
