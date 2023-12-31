# services.py
"""
datetime module is used to manipulate date and time objects in Python
"""
import datetime
import logging
from django.utils import timezone
from django.db import IntegrityError, transaction
from django.core.exceptions import ObjectDoesNotExist
from django_hospital.utils import weekday_mapping
from appointments.serializers import (
    AppointmentResponseSerializer,
    AppointmentRequestAcceptSerializer,
)
from appointments.models import AppointmentRequest
from doctors.models import WorkingHour


# Set up basic logging configuration (example)
logging.basicConfig(
    level=logging.ERROR, format="%(asctime)s - %(levelname)s - %(message)s"
)


@transaction.atomic
def create_appointment_request_service(
    patient_id, doctor_id, preferred_datetime, request_datetime=None
):
    """Create an appointment request for the given patient and doctor, set up request expiration time"""
    # Added request_datetime parameter to enable testing
    print("Request Date Time = ", request_datetime)
    # Get the doctor's working hours for the given day e.g) Monday, Tuesday
    preferred_datetime_day_of_week = weekday_mapping[preferred_datetime.weekday()]
    preferred_time_for_day = (
        preferred_datetime.time()
    )  # Extract time frame for example 09:00 in preferred datetime
    print("Preferred Date Time = ", preferred_datetime)
    doctor_working_hour = WorkingHour.objects.filter(
        doctor_id=doctor_id, day_of_week=preferred_datetime_day_of_week
    ).first()

    if not doctor_working_hour:  # Check Doctor's availiablity for given week day
        logging.error("Doctor is not available at that day")
        return {"error": "Doctor is not available at that day"}

    if (
        preferred_time_for_day < doctor_working_hour.start_time
        or preferred_time_for_day > doctor_working_hour.end_time
    ):  # Preferred time is not included Doctor's working hour
        logging.error("It's not operation hours. Can't make appointment for this time")
        return {
            "error": "It's not operation hours. Can't make appointment for this time"
        }

    if (
        doctor_working_hour.break_start_time is not None
        and doctor_working_hour.break_end_time is not None
    ):  # Doctor can possibly have one break session per workday
        if (
            doctor_working_hour.break_start_time
            <= preferred_time_for_day
            <= doctor_working_hour.break_end_time
        ):
            logging.error(
                "Doctor is having lunch break, can't make appointment for this time"
            )
            return {
                "error": "Doctor is having lunch break, can't make appointment for this time"
            }
    print("request_datetime: ", request_datetime)
    print("doctor_id: ", doctor_id)
    # Setting expiration time
    request_expiration_datetime = set_request_expiration_datetime(
        request_datetime, doctor_id
    )

    # Create and persist an AppointmentRequest
    try:
        appointment_request = AppointmentRequest(
            patient_id=patient_id,
            doctor_id=doctor_id,
            preferred_datetime=preferred_datetime,
            request_expiration_datetime=request_expiration_datetime,
        )
        appointment_request.save()
        # Serialize the appointment request
        serializer = AppointmentResponseSerializer(appointment_request)
        return serializer.data  # Return the serialized data
    except IntegrityError as e:
        logging.error(f"Database error: {e}")
        return {"error": f"Database error: {e}"}
    except ValueError as e:
        logging.error(f"Value error: {e}")
        return {"error": f"Value error: {e}"}
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}")
        return {"error": f"An unexpected error occurred: {e}"}


def set_request_expiration_datetime(
    request_datetime: datetime.datetime, doctor_id
) -> datetime.datetime:
    """Set the expiration time for the appointment request"""
    # Get the doctor's working schedule
    doctor_schedule = WorkingHour.objects.filter(doctor_id=doctor_id)
    print("Doctor schedule = ", doctor_schedule)
    print("Request datetime = ", request_datetime)
    current_time = request_datetime.time()

    # Current day of the week and time
    day_of_week = request_datetime.weekday()  # int

    # Find the relevant working hour object for the day
    working_hour_today = doctor_schedule.filter(
        day_of_week=weekday_mapping[day_of_week]
    ).first()

    if working_hour_today and is_within_working_hours(current_time, working_hour_today):
        if is_during_break(current_time, working_hour_today):
            # If during lunch break, set expiration after the lunch break
            break_end_datetime = datetime.datetime.combine(
                request_datetime.date(), working_hour_today.break_end_time
            )  # Extract date, add time field of working hour
            return break_end_datetime + datetime.timedelta(minutes=15)
        else:
            # If during working hours and not during a break
            return request_datetime + datetime.timedelta(minutes=20)

    # If outside working hours, find the next working period
    next_working_period_start = find_next_working_period_start(
        request_datetime, doctor_schedule
    )

    return next_working_period_start


def is_within_working_hours(current_time, working_hour):
    """Check if the given time is within the working hours"""
    return working_hour.start_time <= current_time <= working_hour.end_time


def is_during_break(current_time, working_hour):
    """Check if the given time is during the break"""
    if working_hour.break_start_time and working_hour.break_end_time:
        return (
            working_hour.break_start_time <= current_time <= working_hour.break_end_time
        )
    return False


def find_next_working_period_start(request_datetime, doctor_schedule):
    """Find the next working period start time after the given datetime"""
    print("find_next request_time: ", request_datetime)
    current_day_index = request_datetime.weekday()  # Monday is 0, Sunday is 6
    print("current_day_index: ", current_day_index)
    print("request_time time: ", request_datetime.time())

    # Iterate days from Monday to Sunday to find next working day
    for days_ahead in range(7):
        # Calculate the day to check
        next_day_index = (current_day_index + days_ahead) % 7
        next_day_name = weekday_mapping[next_day_index]

        # Find the working hours for that day
        next_working_hour = doctor_schedule.filter(day_of_week=next_day_name).first()

        if next_working_hour:
            # If it's a future day or after working hours, use the start time of that day
            next_working_day = request_datetime.date() + datetime.timedelta(
                days=days_ahead
            )
            naive_next_start_time = datetime.datetime.combine(
                next_working_day, next_working_hour.start_time
            )  # Timezone info was not included
            next_start_time = timezone.make_aware(
                naive_next_start_time, request_datetime.tzinfo
            )  # inject time zone information
            if next_start_time > request_datetime:
                return next_start_time + datetime.timedelta(minutes=15)

    # If no working time is found, return None
    return None


def get_appointment_request_list(doctor_id):
    """Get the list of appointment requests for the given doctor"""
    try:
        appointments = AppointmentRequest.objects.filter(doctor_id=doctor_id).exclude(
            status="accepted"
        )
        serializer = AppointmentResponseSerializer(appointments, many=True)
        return serializer.data
    except Exception as e:
        logging.error(
            "An error occurred while retrieving appointment requests for doctor_id %s: %s",
            doctor_id,
            str(e),
        )
        return {"error": "An error occured while retrieving appointment requests"}


def update_appointment_request_status(
    appointment_request_id, new_status, request_datetime: None
):  # request_datetime sends from views as current time value
    """Update the status of the appointment request to 'accepted'"""
    try:
        appointment_request = AppointmentRequest.objects.get(id=appointment_request_id)
        appoinment_request_expiration = (
            appointment_request.request_expiration_datetime
        )  # Extract Request Expiration datetime to compare with the time the request is made

        if (
            request_datetime > appoinment_request_expiration
        ):  # Check whether the appointment request is expired or not
            return {"error": "Appointment request expired"}

        if (
            appointment_request.status != "accepted"
        ):  # Check whether the appointment request is already accepted or not
            appointment_request.status = (
                new_status  # Set appoinment status to 'accepted'
            )
            appointment_request.save()
            serializer = AppointmentRequestAcceptSerializer(appointment_request)
            return serializer.data
        else:
            return {"error": "Appointment request already accepted"}
    except ObjectDoesNotExist:
        return {"error": "Appointment request not found"}
