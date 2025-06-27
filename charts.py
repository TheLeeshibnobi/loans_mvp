import plotly.express as px
import pandas as pd
from supabase import create_client, Client
from datetime import date, timedelta, datetime, UTC
from dotenv import load_dotenv
import os
from overview_metrics import OverviewMetrics

class Charts:
    """Produces the charts needed for the web application"""
    def __init__(self):
        url = os.getenv("SUPABASE_URL")
        service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

        if not url or not service_role_key:
            raise ValueError("SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY is not set.")

        self.supabase: Client = create_client(url, service_role_key)
        self.over_view_tool = OverviewMetrics()

    def borrowers_by_gender(self, days):
        """Returns a pie chart of borrowers by gender for a certain period."""
        get_period = self.over_view_tool.get_period(days)
        period, today = get_period
        start_date = period.isoformat()
        end_date = today.isoformat()

        # Get borrower data from Supabase
        response = (
            self.supabase
            .table('borrowers')
            .select('name', 'gender')
            .gte('created_at', start_date)
            .lte('created_at', end_date)
            .execute()
        )

        # Extract gender data
        genders = [data['gender'] for data in response.data]

        # Count genders
        gender_counts = pd.Series(genders).value_counts().reset_index()
        gender_counts.columns = ['Gender', 'Count']

        # Create pie chart with explicit size
        fig = px.pie(
            gender_counts,
            names='Gender',
            values='Count',
            title='Borrowers by Gender'
        )

        # Update layout for better responsiveness
        fig.update_layout(
            margin=dict(l=10, r=10, t=30, b=10),
            title=dict(font=dict(size=12), x=0.5, xanchor='center'),
            showlegend=True,
            legend=dict(
                font=dict(size=10),
                orientation="h",
                yanchor="bottom",
                y=-0.3,
                xanchor="center",
                x=0.5
            ),
            autosize=True  # Enable autosize
        )

        # Remove fixed width/height from the figure itself
        fig.update_layout(width=None, height=None)

        return fig.to_html(full_html=False, include_plotlyjs='cdn')

    def loan_status_distribution(self, days):
        """Returns loan status distribution donut chart for a given period."""
        get_period = self.over_view_tool.get_period(days)
        period, today = get_period
        start_date = period.isoformat()
        end_date = today.isoformat()

        response = (
            self.supabase
            .table('loans')
            .select('status')
            .gte('created_at', start_date)
            .lte('created_at', end_date)
            .execute()
        )

        # Initialize counts
        data = {
            'Overdue': 0,
            'Active': 0,
            'Completed': 0,
            'Defaulted': 0
        }

        for info in response.data:
            status = info.get('status')
            if status in data:
                data[status] += 1

        # Convert to DataFrame
        data_df = pd.DataFrame({
            'status': list(data.keys()),
            'count': list(data.values())
        })

        # Create donut chart with explicit size
        fig = px.pie(
            data_df,
            names='status',
            values='count',
            hole=0.5,
            title='Loan Status Distribution'
        )

        # Update layout for better responsiveness
        fig.update_layout(
            margin=dict(l=10, r=10, t=30, b=10),
            title=dict(font=dict(size=12), x=0.5, xanchor='center'),
            showlegend=True,
            legend=dict(
                font=dict(size=10),
                orientation="v",
                yanchor="middle",
                y=0.5,
                xanchor="left",
                x=1.1
            ),
            autosize=True  # Enable autosize
        )

        # Remove fixed width/height from the figure itself
        fig.update_layout(width=None, height=None)

        return fig.to_html(full_html=False, include_plotlyjs='cdn')


