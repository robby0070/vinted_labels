# this script 
from google_auth_oauthlib.flow import InstalledAppFlow

# Define the required scopes
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

# Set up the OAuth 2.0 flow
flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)

# Run the flow and authorize the application
credentials = flow.run_local_server(port=0)

# Print the obtained credentials
with open("new_credentials.json", "w") as f:
	f.write(credentials.to_json())
