from supabase import create_client, Client
import datetime
import os
from calendar import monthrange
from collections import Counter, defaultdict

import plotly.express as px
import plotly.graph_objects as go
import pandas as pd


class BusinessAnalytics:
    def __init__(self):
        url = os.getenv("SUPABASE_URL")
        service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

        if not url or not service_role_key:
            raise ValueError("SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY is not set.")

        self.supabase: Client = create_client(url, service_role_key)

    def validate_year(self, year):
        if not isinstance(year, int):
            try:
                year = int(year)
            except (ValueError, TypeError):
                raise ValueError(f"Year must be a valid integer, got: {year}")
        return year

    def month_map(self, year: int):
        if not isinstance(year, int) or not (datetime.MINYEAR <= year <= datetime.MAXYEAR):
            raise ValueError(f"Year must be an integer between {datetime.MINYEAR} and {datetime.MAXYEAR}, got: {year}")

        try:
            month_ranges = {
                month: (
                    f"{year}-{str(i).zfill(2)}-01T00:00:00+00:00",
                    f"{year}-{str(i).zfill(2)}-{monthrange(year, i)[1]}T23:59:59+00:00"
                )
                for i, month in enumerate([
                    "January", "February", "March", "April", "May", "June",
                    "July", "August", "September", "October", "November", "December"
                ], start=1)
            }

            month_ranges["All Months"] = (
                f"{year}-01-01T00:00:00+00:00",
                f"{year}-12-31T23:59:59+00:00"
            )

            return month_ranges
        except Exception as e:
            raise ValueError(f"Error creating month map for year {year}: {str(e)}")

    def apply_gender_filter(self, query, gender):
        if gender == "All":
            return query.or_("gender.eq.Male,gender.eq.Female")
        return query.eq("gender", gender)

    def get_borrower_ids(self, gender):
        query = self.supabase.table("borrowers").select("id")
        query = self.apply_gender_filter(query, gender)
        response = query.execute()
        return [b["id"] for b in response.data]

    def get_loans(self, borrower_ids, start, end, filters=None):
        query = self.supabase.table("loans").select("*")
        query = query.in_("borrower_id", borrower_ids)
        query = query.gte("created_at", start).lte("created_at", end)

        if filters:
            for key, value in filters.items():
                if isinstance(value, list):
                    query = query.in_(key, value)
                else:
                    query = query.eq(key, value)

        return query.execute().data

    def total_loans_issued(self, gender, month, year):
        year = self.validate_year(year)
        start, end = self.month_map(year)[month]
        borrower_ids = self.get_borrower_ids(gender)
        if not borrower_ids:
            return 0

        loans = self.get_loans(borrower_ids, start, end)
        return len(loans)

    def total_revenue_generated(self, gender, month, year):
        year = self.validate_year(year)
        start, end = self.month_map(year)[month]
        borrower_ids = self.get_borrower_ids(gender)
        if not borrower_ids:
            return 0

        # Step 1: Get loan IDs
        loans = self.get_loans(borrower_ids, start, end)
        loan_ids = [loan['id'] for loan in loans if 'id' in loan]
        if not loan_ids:
            return 0

        # Step 2: Get repayment amounts for those loans
        repayment_query = (
            self.supabase
            .table("repayments")
            .select("amount")
            .in_("loan_id", loan_ids)
        )
        repayment_response = repayment_query.execute()
        return sum(item['amount'] for item in repayment_response.data if 'amount' in item)

    def default_rate(self, gender, month, year):
        year = self.validate_year(year)
        start, end = self.month_map(year)[month]
        borrower_ids = self.get_borrower_ids(gender)
        if not borrower_ids:
            return "0%"

        loans = self.get_loans(borrower_ids, start, end)
        if not loans:
            return "0%"

        defaults = self.get_loans(
            borrower_ids, start, end,
            filters={"status": ["Default", "Overdue"]}
        )
        return f"{round(len(defaults) / len(loans) * 100, 2)}%"

    def active_portfolio(self, gender, month, year):
        year = self.validate_year(year)
        start, end = self.month_map(year)[month]
        borrower_ids = self.get_borrower_ids(gender)
        if not borrower_ids:
            return 0

        active_loans = self.get_loans(
            borrower_ids, start, end,
            filters={"status": "Active"}
        )
        return sum(item['amount'] for item in active_loans if 'amount' in item)

    def loan_reason_trend_data(self, gender, year, loan_reason):
        """Returns the number of loans for a specific loan_reason across all months in a year"""
        year = self.validate_year(year)
        borrower_ids = self.get_borrower_ids(gender)
        if not borrower_ids:
            return {}

        monthly_data = {}

        # Loop through all 12 months
        for month in range(1, 13):
            month_name = [
                'January', 'February', 'March', 'April', 'May', 'June',
                'July', 'August', 'September', 'October', 'November', 'December'
            ][month - 1]

            try:
                start, end = self.month_map(year)[month_name]
                # Get all loans within that month
                all_loans = self.get_loans(borrower_ids, start, end)
                # Count loans for the specific reason
                reason_count = sum(1 for loan in all_loans
                                   if loan.get('loan_reason') == loan_reason)
                monthly_data[month_name] = reason_count
            except KeyError:
                # If month doesn't exist in month_map, set to 0
                monthly_data[month_name] = 0

        return monthly_data

    def interest_vs_transaction_costs_data(self, gender, year):
        """returns data of total_interest v.s total_transaction_costs for a certain period"""
        year = self.validate_year(year)
        borrower_ids = self.get_borrower_ids(gender)
        if not borrower_ids:
            return {}

        monthly_data = {}

        # Loop through all 12 months
        for month in range(1, 13):
            month_name = [
                'January', 'February', 'March', 'April', 'May', 'June',
                'July', 'August', 'September', 'October', 'November', 'December'
            ][month - 1]

            try:
                start, end = self.month_map(year)[month_name]
                # Get all loans within that month
                all_loans = self.get_loans(borrower_ids, start, end)

                # Calculate total interest and transaction costs for the month
                total_interest = 0
                total_transaction_costs = 0

                for loan in all_loans:
                    # Calculate interest earned (amount * interest_rate / 100)
                    # Handle None values by defaulting to 0
                    amount = loan.get('amount') or 0
                    interest_rate = loan.get('interest_rate') or 0
                    transaction_cost = loan.get('transaction_costs') or 0

                    # Calculate interest earned for this loan
                    interest_earned = (amount * interest_rate) / 100

                    total_interest += interest_earned
                    total_transaction_costs += transaction_cost

                monthly_data[month_name] = {
                    'total_interest': round(total_interest, 2),
                    'total_transaction_costs': round(total_transaction_costs, 2)
                }

            except KeyError:
                # If month doesn't exist in month_map, set to 0
                monthly_data[month_name] = {
                    'total_interest': 0,
                    'total_transaction_costs': 0
                }

        return monthly_data

    def loan_repayments_vs_discount(self, gender, year):
        """Returns data of total_repaid_loans vs total_discounts for a certain period"""
        year = self.validate_year(year)
        borrower_ids = self.get_borrower_ids(gender)
        if not borrower_ids:
            return {}

        monthly_data = {}

        # Loop through all 12 months
        for month in range(1, 13):
            month_name = [
                'January', 'February', 'March', 'April', 'May', 'June',
                'July', 'August', 'September', 'October', 'November', 'December'
            ][month - 1]

            try:
                start, end = self.month_map(year)[month_name]

                # First, get all loan_ids for the specified borrower_ids
                loans_response = self.supabase.table('loans') \
                    .select('id') \
                    .in_('borrower_id', borrower_ids) \
                    .execute()

                if not loans_response.data:
                    monthly_data[month_name] = {
                        'total_repaid': 0,
                        'total_discount': 0
                    }
                    continue

                loan_ids = [loan['id'] for loan in loans_response.data]

                # Query the repayments table using the correct column names
                response = self.supabase.table('repayments') \
                    .select('amount, discount') \
                    .in_('loan_id', loan_ids) \
                    .gte('repayment_date', start) \
                    .lte('repayment_date', end) \
                    .execute()

                if response.data:
                    total_repaid = sum(row['amount'] or 0 for row in response.data)
                    total_discount = sum(row['discount'] or 0 for row in response.data)

                    monthly_data[month_name] = {
                        'total_repaid': float(total_repaid),
                        'total_discount': float(total_discount)
                    }
                else:
                    monthly_data[month_name] = {
                        'total_repaid': 0,
                        'total_discount': 0
                    }

            except KeyError:
                # If month doesn't exist in month_map, set to 0
                monthly_data[month_name] = {
                    'total_repaid': 0,
                    'total_discount': 0
                }
            except Exception as e:
                # Handle any Supabase API errors
                print(f"Error processing {month_name}: {str(e)}")
                monthly_data[month_name] = {
                    'total_repaid': 0,
                    'total_discount': 0
                }

        return monthly_data


    def loan_reason_trend_chart(self, gender, year, loan_reason):
        """Returns an HTML string of a line chart showing trend for a specific loan reason across months"""
        try:
            trend_data = self.loan_reason_trend_data(gender, year, loan_reason)

            # Check if data is empty
            if not trend_data:
                return "<div>No loan data available for the specified filters.</div>"

            # Convert dictionary to lists for plotting
            months = list(trend_data.keys())
            counts = list(trend_data.values())

            # Create line chart
            fig = go.Figure(data=[go.Scatter(
                x=months,
                y=counts,
                mode='lines+markers',
                line=dict(color='#1f77b4', width=3),
                marker=dict(size=8, color='#1f77b4'),
                text=counts,
                textposition='top center',
                textfont=dict(size=10),
                name=f'{loan_reason}',
                hovertemplate='<b>%{x}</b><br>Loans: %{y}<extra></extra>'
            )])

            # Update layout
            fig.update_layout(
                title={
                    'text': f'Loan Trend for "{loan_reason}" - {gender.title()} ({year})',
                    'x': 0.5,
                    'xanchor': 'center',
                    'font': {'size': 16, 'family': 'Arial, sans-serif'}
                },
                xaxis_title='Month',
                yaxis_title='Number of Loans',
                font=dict(size=10),
                margin=dict(l=60, r=20, t=60, b=80),
                xaxis=dict(
                    tickangle=45,  # Rotate x-axis labels for better readability
                    tickfont=dict(size=9)
                ),
                yaxis=dict(
                    tickfont=dict(size=10),
                    rangemode='tozero'  # Start y-axis from 0
                ),
                showlegend=False
            )

            # Convert to HTML string
            html_string = fig.to_html(include_plotlyjs='cdn', full_html=False, config={'responsive': True})

            return html_string
        except Exception as e:
            return f"<div>Error generating chart: {str(e)}</div>"

    def interest_vs_transaction_costs_chart(self, gender, year):
        """Returns an HTML string of a clustered bar chart comparing interest earned vs transaction costs"""
        try:
            chart_data = self.interest_vs_transaction_costs_data(gender, year)

            # Check if data is empty
            if not chart_data:
                return "<div>No financial data available for the specified filters.</div>"

            # Convert dictionary to lists for plotting
            months = list(chart_data.keys())
            interest_values = [chart_data[month]['total_interest'] for month in months]
            transaction_costs = [chart_data[month]['total_transaction_costs'] for month in months]

            # Create clustered bar chart
            fig = go.Figure()

            # Add Interest Earned bars
            fig.add_trace(go.Bar(
                x=months,
                y=interest_values,
                name='Interest Earned',
                marker_color='#2E8B57',  # Sea Green
                text=[f'${val:,.0f}' if val > 0 else '' for val in interest_values],
                textposition='outside',
                textfont=dict(size=9),
                hovertemplate='<b>%{x}</b><br>Interest Earned: $%{y:,.2f}<extra></extra>'
            ))

            # Add Transaction Costs bars
            fig.add_trace(go.Bar(
                x=months,
                y=transaction_costs,
                name='Transaction Costs',
                marker_color='#DC143C',  # Crimson
                text=[f'${val:,.0f}' if val > 0 else '' for val in transaction_costs],
                textposition='outside',
                textfont=dict(size=9),
                hovertemplate='<b>%{x}</b><br>Transaction Costs: $%{y:,.2f}<extra></extra>'
            ))

            # Update layout
            fig.update_layout(
                title={
                    'text': f'Interest Earned vs Transaction Costs - {gender.title()} ({year})',
                    'x': 0.5,
                    'xanchor': 'center',
                    'font': {'size': 16, 'family': 'Arial, sans-serif'}
                },
                xaxis_title='Month',
                yaxis_title='Amount ($)',
                font=dict(size=10),
                margin=dict(l=60, r=20, t=80, b=80),
                xaxis=dict(
                    tickangle=45,  # Rotate x-axis labels for better readability
                    tickfont=dict(size=9)
                ),
                yaxis=dict(
                    tickfont=dict(size=10),
                    rangemode='tozero',  # Start y-axis from 0
                    tickformat='$,.0f'  # Format y-axis as currency
                ),
                barmode='group',  # This creates the clustered/grouped bar effect
                showlegend=True,
                legend=dict(
                    orientation="h",
                    yanchor="bottom",
                    y=1.02,
                    xanchor="right",
                    x=1
                ),
                plot_bgcolor='rgba(0,0,0,0)',  # Transparent background
                paper_bgcolor='rgba(0,0,0,0)'
            )

            # Add grid lines for better readability
            fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor='lightgray')

            # Convert to HTML string
            html_string = fig.to_html(include_plotlyjs='cdn', full_html=False, config={'responsive': True})

            return html_string
        except Exception as e:
            return f"<div>Error generating chart: {str(e)}</div>"

    def loan_repayments_vs_discount_chart(self, gender, year):
        """Returns an HTML string of a clustered bar chart comparing loan repayments vs discounts given"""
        try:
            chart_data = self.loan_repayments_vs_discount(gender, year)

            # Check if data is empty
            if not chart_data:
                return "<div>No repayment data available for the specified filters.</div>"

            # Convert dictionary to lists for plotting
            months = list(chart_data.keys())
            repayment_values = [chart_data[month]['total_repaid'] for month in months]
            discount_values = [chart_data[month]['total_discount'] for month in months]

            # Create clustered bar chart
            fig = go.Figure()

            # Add Total Repaid bars
            fig.add_trace(go.Bar(
                x=months,
                y=repayment_values,
                name='Total Repaid',
                marker_color='#4169E1',  # Royal Blue
                text=[f'${val:,.0f}' if val > 0 else '' for val in repayment_values],
                textposition='outside',
                textfont=dict(size=9),
                hovertemplate='<b>%{x}</b><br>Total Repaid: $%{y:,.2f}<extra></extra>'
            ))

            # Add Discounts Given bars
            fig.add_trace(go.Bar(
                x=months,
                y=discount_values,
                name='Discounts Given',
                marker_color='#FF6347',  # Tomato
                text=[f'${val:,.0f}' if val > 0 else '' for val in discount_values],
                textposition='outside',
                textfont=dict(size=9),
                hovertemplate='<b>%{x}</b><br>Discounts Given: $%{y:,.2f}<extra></extra>'
            ))

            # Update layout
            fig.update_layout(
                title={
                    'text': f'Loan Repayments vs Discounts Given - {gender.title()} ({year})',
                    'x': 0.5,
                    'xanchor': 'center',
                    'font': {'size': 16, 'family': 'Arial, sans-serif'}
                },
                xaxis_title='Month',
                yaxis_title='Amount ($)',
                font=dict(size=10),
                margin=dict(l=60, r=20, t=80, b=80),
                xaxis=dict(
                    tickangle=45,  # Rotate x-axis labels for better readability
                    tickfont=dict(size=9)
                ),
                yaxis=dict(
                    tickfont=dict(size=10),
                    rangemode='tozero',  # Start y-axis from 0
                    tickformat='$,.0f'  # Format y-axis as currency
                ),
                barmode='group',  # This creates the clustered/grouped bar effect
                showlegend=True,
                legend=dict(
                    orientation="h",
                    yanchor="bottom",
                    y=1.02,
                    xanchor="right",
                    x=1
                ),
                plot_bgcolor='rgba(0,0,0,0)',  # Transparent background
                paper_bgcolor='rgba(0,0,0,0)'
            )

            # Add grid lines for better readability
            fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor='lightgray')

            # Convert to HTML string
            html_string = fig.to_html(include_plotlyjs='cdn', full_html=False, config={'responsive': True})

            return html_string
        except Exception as e:
            return f"<div>Error generating chart: {str(e)}</div>"



