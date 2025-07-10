"""Utility functions for Google Calendar integration."""

import datetime
import json
import os
import pathlib

from google.auth.transport import requests
from google.oauth2 import credentials
from google_auth_oauthlib import flow
from googleapiclient import discovery

Path = pathlib.Path
datetime = datetime.datetime
Request = requests.Request
build = discovery.build
InstalledAppFlow = flow.InstalledAppFlow
Credentials = credentials.Credentials

# Define scopes needed for Google Calendar
SCOPES = ["https://www.googleapis.com/auth/calendar"]

# Path for token storage
TOKEN_PATH = Path(os.path.expanduser("~/.credentials/calendar_token.json"))
CREDENTIALS_PATH = Path("credentials.json")


def get_calendar_service():
  """Authenticate and create a Google Calendar service object.

  Returns:
      A Google Calendar service object or None if authentication fails
  """
  creds = None

  # Check if token exists and is valid
  if TOKEN_PATH.exists():
    creds = Credentials.from_authorized_user_info(
        json.loads(TOKEN_PATH.read_text()), SCOPES
    )

  # If credentials don't exist or are invalid, refresh or get new ones
  if not creds or not creds.valid:
    if creds and creds.expired and creds.refresh_token:
      creds.refresh(Request())
    else:
      # If credentials.json doesn't exist, we can't proceed with OAuth flow
      if not CREDENTIALS_PATH.exists():
        print(
            f"Error: {CREDENTIALS_PATH} not found. Please follow setup"
            " instructions."
        )
        return None

      flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
      creds = flow.run_local_server(port=0)

    # Save the credentials for the next run
    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_PATH.write_text(creds.to_json())

  # Create and return the Calendar service
  return build("calendar", "v3", credentials=creds)


def format_event_time(event_time):
  """Format an event time into a human-readable string.

  Args:
      event_time (dict): The event time dictionary from Google Calendar API

  Returns:
      str: A human-readable time string
  """
  if "dateTime" in event_time:
    # This is a datetime event
    dt = datetime.fromisoformat(event_time["dateTime"].replace("Z", "+00:00"))
    return dt.strftime("%Y-%m-%d %I:%M %p")
  elif "date" in event_time:
    # This is an all-day event
    return f"{event_time['date']} (All day)"
  return "Unknown time format"


def parse_datetime(datetime_str):
  """Parse a datetime string into a datetime object.

  Args:
      datetime_str (str): A string representing a date and time

  Returns:
      datetime: A datetime object or None if parsing fails
  """
  formats = [
      "%Y-%m-%d %H:%M",
      "%Y-%m-%d %I:%M %p",
      "%Y-%m-%d",
      "%m/%d/%Y %H:%M",
      "%m/%d/%Y %I:%M %p",
      "%m/%d/%Y",
      "%B %d, %Y %H:%M",
      "%B %d, %Y %I:%M %p",
      "%B %d, %Y",
  ]

  for fmt in formats:
    try:
      return datetime.strptime(datetime_str, fmt)
    except ValueError:
      continue

  return None


def get_current_time() -> dict:
  """Get the current time and date."""
  now = datetime.now()

  # Format date as MM-DD-YYYY
  formatted_date = now.strftime("%m-%d-%Y")

  return {
      "current_time": now.strftime("%Y-%m-%d %H:%M:%S"),
      "formatted_date": formatted_date,
  }


def create_event(
    summary: str,
    start_time: str,
    end_time: str,
    attendees: list = None,
) -> dict:
  """Create a new event in Google Calendar.

  Args:
      summary (str): Event title/summary
      start_time (str): Start time (e.g., "2023-12-31 14:00")
      end_time (str): End time (e.g., "2023-12-31 15:00")
      attendees (list): List of attendees' email addresses

  Returns:
      dict: Information about the created event or error details
  """
  try:
    # Get calendar service
    service = get_calendar_service()
    if not service:
      return {
          "status": "error",
          "message": (
              "Failed to authenticate with Google Calendar. Please check"
              " credentials."
          ),
      }

    # Always use primary calendar
    calendar_id = "primary"

    # Parse times
    start_dt = parse_datetime(start_time)
    end_dt = parse_datetime(end_time)

    if not start_dt or not end_dt:
      return {
          "status": "error",
          "message": (
              "Invalid date/time format. Please use YYYY-MM-DD HH:MM format."
          ),
      }

    # Dynamically determine timezone
    timezone_id = "America/New_York"  # Default to Eastern Time

    try:
      # Try to get the timezone from the calendar settings
      settings = service.settings().list().execute()
      for setting in settings.get("items", []):
        if setting.get("id") == "timezone":
          timezone_id = setting.get("value")
          break
    except Exception:
      # If we can't get it from settings, we'll use the default
      pass

    # Create event body without type annotations
    event_body = {}

    # Add summary
    event_body["summary"] = summary

    # Add start and end times with the dynamically determined timezone
    event_body["start"] = {
        "dateTime": start_dt.isoformat(),
        "timeZone": timezone_id,
    }
    event_body["end"] = {
        "dateTime": end_dt.isoformat(),
        "timeZone": timezone_id,
    }
    event_body["attendees"] = [{"email": attendee} for attendee in attendees]

    # Call the Calendar API to create the event
    event = (
        service.events()
        .insert(calendarId=calendar_id, body=event_body)
        .execute()
    )

    return {
        "status": "success",
        "message": "Event created successfully",
        "event_id": event["id"],
        "event_link": event.get("htmlLink", ""),
    }

  except Exception as e:
    return {"status": "error", "message": f"Error creating event: {str(e)}"}


def delete_event(
    event_id: str,
    confirm: bool,
) -> dict:
  """Delete an event from Google Calendar.

  Args:
      event_id (str): The unique ID of the event to delete
      confirm (bool): Confirmation flag (must be set to True to delete)

  Returns:
      dict: Operation status and details
  """
  # Safety check - require explicit confirmation
  if not confirm:
    return {
        "status": "error",
        "message": "Please confirm deletion by setting confirm=True",
    }

  try:
    # Get calendar service
    service = get_calendar_service()
    if not service:
      return {
          "status": "error",
          "message": (
              "Failed to authenticate with Google Calendar. Please check"
              " credentials."
          ),
      }

    # Always use primary calendar
    calendar_id = "primary"

    # Call the Calendar API to delete the event
    service.events().delete(calendarId=calendar_id, eventId=event_id).execute()

    return {
        "status": "success",
        "message": f"Event {event_id} has been deleted successfully",
        "event_id": event_id,
    }

  except Exception as e:
    return {"status": "error", "message": f"Error deleting event: {str(e)}"}


def edit_event(
    event_id: str,
    summary: str,
    start_time: str,
    end_time: str,
) -> dict:
  """Edit an existing event in Google Calendar - change title and/or reschedule.

  Args:
      event_id (str): The ID of the event to edit
      summary (str): New title/summary for the event (pass empty string to keep
        unchanged)
      start_time (str): New start time (e.g., "2023-12-31 14:00", pass empty
        string to keep unchanged)
      end_time (str): New end time (e.g., "2023-12-31 15:00", pass empty string
        to keep unchanged)

  Returns:
      dict: Information about the edited event or error details
  """
  try:
    # Get calendar service
    service = get_calendar_service()
    if not service:
      return {
          "status": "error",
          "message": (
              "Failed to authenticate with Google Calendar. Please check"
              " credentials."
          ),
      }

    # Always use primary calendar
    calendar_id = "primary"

    # First get the existing event
    try:
      event = (
          service.events()
          .get(calendarId=calendar_id, eventId=event_id)
          .execute()
      )
    except Exception:
      return {
          "status": "error",
          "message": f"Event with ID {event_id} not found in primary calendar.",
      }

    # Update the event with new values
    if summary:
      event["summary"] = summary

    # Get timezone from the original event
    timezone_id = "America/New_York"  # Default
    if "start" in event and "timeZone" in event["start"]:
      timezone_id = event["start"]["timeZone"]

    # Update start time if provided
    if start_time:
      start_dt = parse_datetime(start_time)
      if not start_dt:
        return {
            "status": "error",
            "message": (
                "Invalid start time format. Please use YYYY-MM-DD HH:MM format."
            ),
        }
      event["start"] = {
          "dateTime": start_dt.isoformat(),
          "timeZone": timezone_id,
      }

    # Update end time if provided
    if end_time:
      end_dt = parse_datetime(end_time)
      if not end_dt:
        return {
            "status": "error",
            "message": (
                "Invalid end time format. Please use YYYY-MM-DD HH:MM format."
            ),
        }
      event["end"] = {"dateTime": end_dt.isoformat(), "timeZone": timezone_id}

    # Update the event
    updated_event = (
        service.events()
        .update(calendarId=calendar_id, eventId=event_id, body=event)
        .execute()
    )

    return {
        "status": "success",
        "message": "Event updated successfully",
        "event_id": updated_event["id"],
        "event_link": updated_event.get("htmlLink", ""),
    }

  except Exception as e:
    return {"status": "error", "message": f"Error updating event: {str(e)}"}


def list_events(
    start_date: str,
    days: int,
) -> dict:
  """List upcoming calendar events within a specified date range.

  Args:
      start_date (str): Start date in YYYY-MM-DD format. If empty string,
        defaults to today.
      days (int): Number of days to look ahead. Use 1 for today only, 7 for a
        week, 30 for a month, etc.

  Returns:
      dict: Information about upcoming events or error details
  """
  try:
    print("Listing events")
    print("Start date: ", start_date)
    print("Days: ", days)
    # Get calendar service
    service = get_calendar_service()
    if not service:
      return {
          "status": "error",
          "message": (
              "Failed to authenticate with Google Calendar. Please check"
              " credentials."
          ),
          "events": [],
      }

    # Always use a large max_results value to return all events
    max_results = 100

    # Always use primary calendar
    calendar_id = "primary"

    # Set time range
    if not start_date or start_date.strip() == "":
      start_time = datetime.datetime.utcnow()
    else:
      try:
        start_time = datetime.datetime.strptime(start_date, "%Y-%m-%d")
      except ValueError:
        return {
            "status": "error",
            "message": (
                f"Invalid date format: {start_date}. Use YYYY-MM-DD format."
            ),
            "events": [],
        }

    # If days is not provided or is invalid, default to 1 day
    if not days or days < 1:
      days = 1

    end_time = start_time + datetime.timedelta(days=days)

    # Format times for API call
    time_min = start_time.isoformat() + "Z"
    time_max = end_time.isoformat() + "Z"

    # Call the Calendar API
    events_result = (
        service.events()
        .list(
            calendarId=calendar_id,
            timeMin=time_min,
            timeMax=time_max,
            maxResults=max_results,
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )

    events = events_result.get("items", [])

    if not events:
      return {
          "status": "success",
          "message": "No upcoming events found.",
          "events": [],
      }

    # Format events for display
    formatted_events = []
    for event in events:
      formatted_event = {
          "id": event.get("id"),
          "summary": event.get("summary", "Untitled Event"),
          "start": format_event_time(event.get("start", {})),
          "end": format_event_time(event.get("end", {})),
          "location": event.get("location", ""),
          "description": event.get("description", ""),
          "attendees": [
              attendee.get("email")
              for attendee in event.get("attendees", [])
              if "email" in attendee
          ],
          "link": event.get("htmlLink", ""),
      }
      formatted_events.append(formatted_event)

    return {
        "status": "success",
        "message": f"Found {len(formatted_events)} event(s).",
        "events": formatted_events,
    }

  except Exception as e:
    return {
        "status": "error",
        "message": f"Error fetching events: {str(e)}",
        "events": [],
    }
