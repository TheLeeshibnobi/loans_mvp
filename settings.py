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
            # Validate input
            if not key or not key.strip():
                return {"success": False, "message": "Secret key cannot be empty."}

            # Check if key already exists to prevent duplicates
            existing = self.supabase.table("secret_keys").select("key").eq("key", key.strip()).execute()
            if existing.data and len(existing.data) > 0:
                return {"success": False, "message": "Secret key already exists."}

            data = {
                "key": key.strip(),
                "created_at": datetime.datetime.now(datetime.UTC).isoformat()
            }

            print(f"Attempting to insert data: {data}")
            response = self.supabase.table("secret_keys").insert(data).execute()

            # Check for errors in the response
            if hasattr(response, 'error') and response.error:
                print(f"Supabase error: {response.error}")
                return {"success": False, "message": f"Database error: {response.error}"}

            # Verify the insertion was successful
            if response.data and len(response.data) > 0:
                print(f"Insert successful: {response}")
                return {"success": True, "message": "Secret key saved successfully.", "data": response.data}
            else:
                return {"success": False, "message": "Failed to save secret key - no data returned."}

        except Exception as e:
            print(f"Error in save_secret_key: {str(e)}")
            return {"success": False, "message": f"Unexpected error: {str(e)}"}

    def delete_expired_keys(self, hours: int = 24):
        """Deletes secret keys older than the specified number of hours (default: 24)."""
        try:
            # Validate input
            if hours <= 0:
                return {"success": False, "message": "Hours must be a positive number."}

            cutoff = (datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=hours)).isoformat()

            # First, check if there are any keys to delete
            check_response = self.supabase.table("secret_keys").select("id").lt("created_at", cutoff).execute()

            if not check_response.data or len(check_response.data) == 0:
                return {"success": True, "message": "No expired keys found to delete.", "deleted_count": 0}

            keys_to_delete = len(check_response.data)

            # Proceed with deletion
            response = self.supabase.table("secret_keys").delete().lt("created_at", cutoff).execute()

            if hasattr(response, 'error') and response.error:
                print(f"Supabase error in delete: {response.error}")
                return {"success": False, "message": f"Database error: {response.error}"}

            # Check if deletion was successful
            deleted_count = len(response.data) if response.data else keys_to_delete
            return {
                "success": True,
                "message": f"Successfully deleted {deleted_count} expired key(s).",
                "deleted_count": deleted_count
            }

        except Exception as e:
            print(f"Error in delete_expired_keys: {str(e)}")
            return {"success": False, "message": f"Unexpected error: {str(e)}"}

    def get_all_secret_keys(self):
        """Retrieves all secret keys from the database (for admin purposes)."""
        try:
            response = self.supabase.table("secret_keys").select("*").order("created_at", desc=True).execute()

            if hasattr(response, 'error') and response.error:
                print(f"Supabase error: {response.error}")
                return {"success": False, "message": f"Database error: {response.error}"}

            if not response.data:
                return {"success": True, "message": "No secret keys found.", "data": []}

            return {
                "success": True,
                "message": f"Retrieved {len(response.data)} secret key(s).",
                "data": response.data
            }

        except Exception as e:
            print(f"Error in get_all_secret_keys: {str(e)}")
            return {"success": False, "message": f"Unexpected error: {str(e)}"}

    def count_secret_keys(self):
        """Returns the count of secret keys in the database."""
        try:
            response = self.supabase.table("secret_keys").select("id", count="exact").execute()

            if hasattr(response, 'error') and response.error:
                print(f"Supabase error: {response.error}")
                return {"success": False, "message": f"Database error: {response.error}"}

            count = response.count if hasattr(response, 'count') else (len(response.data) if response.data else 0)

            return {
                "success": True,
                "message": f"Found {count} secret key(s) in database.",
                "count": count
            }

        except Exception as e:
            print(f"Error in count_secret_keys: {str(e)}")
            return {"success": False, "message": f"Unexpected error: {str(e)}"}

    def delete_secret_key_by_id(self, key_id: int):
        """Deletes a specific secret key by its ID."""
        try:
            # Validate input
            if not key_id or not isinstance(key_id, (int, str)):
                return {"success": False, "message": "Invalid key ID provided."}

            # Check if the key exists
            existing = self.supabase.table("secret_keys").select("id").eq("id", key_id).execute()

            if not existing.data or len(existing.data) == 0:
                return {"success": False, "message": "Secret key not found."}

            # Delete the key
            response = self.supabase.table("secret_keys").delete().eq("id", key_id).execute()

            if hasattr(response, 'error') and response.error:
                print(f"Supabase error in delete: {response.error}")
                return {"success": False, "message": f"Database error: {response.error}"}

            if response.data and len(response.data) > 0:
                return {"success": True, "message": "Secret key deleted successfully."}
            else:
                return {"success": False, "message": "Failed to delete secret key."}

        except Exception as e:
            print(f"Error in delete_secret_key_by_id: {str(e)}")
            return {"success": False, "message": f"Unexpected error: {str(e)}"}

    def cleanup_database(self, hours: int = 24):
        """Comprehensive cleanup method that removes expired keys and returns cleanup statistics."""
        try:
            # Get count before cleanup
            before_count = self.count_secret_keys()
            if not before_count["success"]:
                return before_count

            # Perform cleanup
            cleanup_result = self.delete_expired_keys(hours)
            if not cleanup_result["success"]:
                return cleanup_result

            # Get count after cleanup
            after_count = self.count_secret_keys()
            if not after_count["success"]:
                return after_count

            return {
                "success": True,
                "message": f"Cleanup completed. Removed {cleanup_result.get('deleted_count', 0)} expired key(s).",
                "before_count": before_count["count"],
                "after_count": after_count["count"],
                "deleted_count": cleanup_result.get("deleted_count", 0)
            }

        except Exception as e:
            print(f"Error in cleanup_database: {str(e)}")
            return {"success": False, "message": f"Cleanup failed: {str(e)}"}