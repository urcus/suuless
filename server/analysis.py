"""Calendar-day comparisons on exact historical amounts, without currency conversion."""
from decimal import Decimal
from .international import money


def percentage(value, reference):
    return round(float((Decimal(value) - Decimal(reference)) * 100 / Decimal(reference)), 2) if reference else None


def analyze(daily, previous, currency, previous_start, previous_end, includes_today):
    days = len(daily)
    quantities = [day['quantity'] for day in daily]
    quantity = sum(quantities)
    average = Decimal(quantity) / days
    previous_quantity = sum(day['quantity'] for day in previous)
    codes = sorted({code for day in daily + previous for code in day['amounts']} or {currency})
    amounts = {code: sum(day['amounts'].get(code, 0) for day in daily) for code in codes}
    previous_amounts = {code: sum(day['amounts'].get(code, 0) for day in previous) for code in codes}
    averages = {code: Decimal(amounts[code]) / days for code in codes}
    return dict(
        includes_today=includes_today,
        average_quantity_per_day=round(float(average), 2),
        average_cost_per_day={code: money(averages[code], code) for code in codes},
        days_with_entries=sum(value > 0 for value in quantities),
        minimum_quantity=min(quantities), maximum_quantity=max(quantities),
        previous_period=dict(start=previous_start, end=previous_end, days=len(previous),
                             quantity=previous_quantity,
                             costs={code: money(previous_amounts[code], code) for code in codes}),
        comparison=dict(
            quantity_delta=quantity-previous_quantity if previous else None,
            quantity_percent=percentage(quantity, previous_quantity) if previous else None,
            cost_deltas={code: money(amounts[code]-previous_amounts[code], code) for code in codes} if previous else {},
            cost_percent={code: percentage(amounts[code], previous_amounts[code]) for code in codes} if previous else {}),
        daily=[dict(date=day['date'], quantity=day['quantity'],
                    costs={code: money(day['amounts'].get(code, 0), code) for code in codes},
                    quantity_delta=round(float(Decimal(day['quantity'])-average), 2),
                    quantity_percent=percentage(day['quantity'], average),
                    cost_deltas={code: money(Decimal(day['amounts'].get(code, 0))-averages[code], code) for code in codes},
                    cost_percent={code: percentage(day['amounts'].get(code, 0), averages[code]) for code in codes}) for day in daily])
