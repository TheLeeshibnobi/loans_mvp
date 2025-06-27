import os
import datetime
from supabase import create_client, Client


class Settings:
    def __init__(self):
        url = os.getenv("SUPABASE_URL")
        service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

        if not url or not service_role_key:
            raise ValueError("SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY is not set.")

        self.supabase: Client = create_client(url, service_role_key)

    def save_secret_key(self, key: str):
        """Saves a secret key to the database with current UTC timestamp."""
        try:
            data = {
                "key": key,
                "created_at": datetime.datetime.now(datetime.UTC).isoformat()
            }

            print(f"Attempting to insert data: {data}")
            response = self.supabase.table("secret_keys").insert(data).execute()

            # Check for errors in the response
            if hasattr(response, 'error') and response.error:
                print(f"Supabase error: {response.error}")
                raise Exception(f"Database error: {response.error}")

            print(f"Insert response: {response}")
            return response

        except Exception as e:
            print(f"Error in save_secret_key: {str(e)}")
            raise

    def delete_expired_keys(self, hours: int = 24):
        """Deletes secret keys older than the specified number of hours (default: 24)."""
        try:
            cutoff = (datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=hours)).isoformat()
            response = self.supabase.table("secret_keys").delete().lt("created_at", cutoff).execute()

            if hasattr(response, 'error') and response.error:
                print(f"Supabase error in delete: {response.error}")
                raise Exception(f"Database error: {response.error}")

            return response
        except Exception as e:
            print(f"Error in delete_expired_keys: {str(e)}")
            raise