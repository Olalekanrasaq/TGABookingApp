import streamlit as st
from datetime import datetime, timedelta
import json
import pandas as pd
import streamlit.components.v1
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import os

db_file = "bookings.json"
image_folder = "uploaded_images"

# Authenticate Google Drive using OAuth 2.0
@st.cache_resource
def authenticate_drive(credentials_file):
    creds = None
    # The credentials.json file should contain the OAuth 2.0 credentials.
    if os.path.exists(credentials_file):
        creds = Credentials.from_authorized_user_file(credentials_file, scopes=["https://www.googleapis.com/auth/drive.file"])

    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                credentials_file, scopes=["https://www.googleapis.com/auth/drive.file"]
            )
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open(credentials_file, 'w') as token:
            token.write(creds.to_json())
    
    # Build the Google Drive API client
    drive_service = build("drive", "v3", credentials=creds)
    return drive_service


drive_service = authenticate_drive("credentials.json")

def upload_to_drive(file_path, folder_id, drive_service):
    """
    Upload or update a file in the specified Google Drive folder.
    """
    # Check if the file already exists in the folder
    query = f"'{folder_id}' in parents and trashed=false"
    results = drive_service.files().list(q=query).execute()
    files = results.get('files', [])
    
    existing_file = None
    for file in files:
        if file['name'] == "bookings.json":
            existing_file = file
            break

    # If file exists, update it; otherwise, create a new one
    if existing_file:
        # Update existing file
        file_id = existing_file['id']
        media = MediaFileUpload(file_path, mimetype='application/json')
        drive_service.files().update(fileId=file_id, media_body=media).execute()
        return f"Updated: {existing_file['webViewLink']}"
    else:
        # Create new file
        file_metadata = {'name': 'bookings.json', 'parents': [folder_id]}
        media = MediaFileUpload(file_path, mimetype='application/json')
        file = drive_service.files().create(body=file_metadata, media_body=media, fields='id, webViewLink').execute()
        return f"Created: {file['webViewLink']}"

with open(db_file, "r") as file:
    bookings = json.load(file)

st.title("Booking App")
st.markdown("---")

st.sidebar.header("TGA Booking")

selection = st.sidebar.radio("Request", 
                             ["Booking Calendar", "Book Apartment", 
                              "Check Previous Booking"])

if selection == "Booking Calendar":
    st.info("Dates colored red have been booked")
    # Adjust end dates in the booking data
    for booking in bookings:
        booking["check_out"] = (datetime.strptime(booking["check_out"], "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
    # Convert booking data into JSON-like structure for FullCalendar
    events = [
        {"title": booking["apartment"], "start": booking["check_in"], "end": booking["check_out"]}
        for booking in bookings
    ]

    # FullCalendar.js with selectable dates
    fullcalendar_code = f"""
    <!DOCTYPE html>
    <html>
    <head>
    <link href="https://cdn.jsdelivr.net/npm/fullcalendar@5.11.3/main.min.css" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/fullcalendar@5.11.3/main.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/fullcalendar@5.11.3/locales-all.min.js"></script>
    <style>
        .fc-event-title {{
        text-align: center;
        font-weight: bold;
        font-size: 1.2em;
        }}
    </style>
    </head>
    <body>
    <div id="calendar"></div>
    <script>
        document.addEventListener('DOMContentLoaded', function() {{
        var calendarEl = document.getElementById('calendar');
        var calendar = new FullCalendar.Calendar(calendarEl, {{
            initialView: 'dayGridMonth',
            selectable: true,
            events: {events},  // Inject event data
            eventColor: '#FF0000',  // Set event color to red
        }});
        calendar.render();
        }});
    </script>
    </body>
    </html>
    """

    # JavaScript and Python communication handler
    streamlit.components.v1.html(fullcalendar_code, height=500)

    # Button to show the booking record checker
    info_button = st.button("Check booking record")

    if info_button or "check_booking_triggered" in st.session_state:
        st.session_state.check_booking_triggered = True  # Persist state for this section
        
        # Inputs for booking record check
        check_in_date = st.date_input("Check-In date", key="check_in_date")
        apartment = st.selectbox(
            "Choose apartment",
            ["Upper floor", "Middle floor", "Ground floor"],
            key="apartment_choice"
        )

        # Button to trigger the check
        submit = st.button("Check", key="submit_check")

        if submit:
            # Check the booking record
            records = []
            for booking in bookings:
                if booking["check_in"] == check_in_date.isoformat() and booking["apartment"] == apartment:
                    records.append(booking)
                    break
            else:
                st.error(f"No booking is available for {apartment} on the selected date")

            # Display the result as a table
            if records:
                df = pd.DataFrame(records)
                # Render the table with images
                st.markdown(df.to_html(escape=False, index=False), unsafe_allow_html=True)
                #st.table(df)


elif selection == "Book Apartment":
    st.subheader("Book Apartment")
    name = st.text_input("Name of the Customer")
    address = st.text_input("Address")
    phone = st.text_input("Phone Number")
    email = st.text_input("Email")
    apartment = st.selectbox("Choose apartment", 
                             ["Upper floor", "Middle floor", "Ground floor"])
    check_in = st.date_input("Check-In date")
    check_out = st.date_input("Check-Out date")
    upload_image = st.file_uploader("Upload ID card", type=["JPG", "JPEG", "PNG"])

    submit = st.button("Book")

    if submit:
        # Validate if the booking dates overlap
        overlap = False
        for booking in bookings:
            if booking["apartment"] == apartment:
                existing_check_in = datetime.fromisoformat(booking["check_in"]).date()
                existing_check_out = datetime.fromisoformat(booking["check_out"]).date()
                
                # Check for overlap
                if (check_in <= existing_check_out and check_out >= existing_check_in):
                    overlap = True
                    break

        if overlap:
            st.error("This apartment is already booked for the selected dates. Please choose different dates.")
        else:
            # No overlap, proceed with booking

            # Save the uploaded image locally
            timestamp = datetime.now().strftime("%Y%m%d")
            image_filename = f"{name.replace(' ', '_')}_{timestamp}.jpg"

            with open(image_filename, "wb") as f:
                f.write(upload_image.getbuffer())

            # Upload the image to Google Drive
            folder_id = '1XTXmX8NfnzuDSwtIuHfsiGAnUS8HtTOc'
            file_metadata = {'name': image_filename, 'parents': [folder_id]}
            media = MediaFileUpload(image_filename, mimetype='image/jpeg')
            file = drive_service.files().create(body=file_metadata, media_body=media, fields='id').execute()

            # Get the file link
            image_link = f'<a href="https://drive.google.com/file/d/{file["id"]}/view?usp=sharing" target="_blank">View image</a>'
            
            book_dict = {
                "name": name.title(),
                "address": address,
                "phone": phone,
                "email": email,
                "apartment": apartment,
                "check_in": check_in.isoformat(),
                "check_out": check_out.isoformat(),
                "days": (check_out - check_in).days,
                "image_link": image_link
            }

            bookings.append(book_dict)
            
            # Save bookings to the database file
            with open(db_file, "w") as file:
                json.dump(bookings, file, indent=4)

            # Upload to Google Drive
            drive_link = upload_to_drive("bookings.json", "1XTXmX8NfnzuDSwtIuHfsiGAnUS8HtTOc", drive_service)

            st.success("Room has been booked successfully!!")

elif selection == "Check Previous Booking":
    st.subheader("Previous Booking")
    df = pd.DataFrame(bookings)
    # Render the table with images
    st.markdown(df.to_html(escape=False, index=False), unsafe_allow_html=True)

elif selection == "Download booking data":
    with open(db_file, "r") as file:
        json_data = file.read()
    st.download_button("Download Booking Data", json_data, "bookings.json")
