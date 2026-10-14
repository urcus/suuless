"""Calendar-day comparisons on exact historical amounts, without currency conversion."""
from datetime import date, datetime
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
    result = dict(
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
    result['trend'] = []
    for index, day in enumerate(daily):
        window = daily[max(0, index - 6):index + 1]
        q = Decimal(sum(item['quantity'] for item in window)) / len(window)
        costs = {code: sum(item['amounts'].get(code, 0) for item in window) / Decimal(len(window)) for code in codes}
        result['trend'].append(dict(date=day['date'], window_days=len(window), quantity=round(float(q), 2),
                                    costs={code: money(costs[code], code) for code in codes},
                                    quantity_delta=round(float(q-average), 2),
                                    cost_deltas={code: money(costs[code]-averages[code], code) for code in codes}))
    return result


def habits(daily, rows, tz, includes_today, currency):
    """Wall-clock habits and a 30-day estimate from completed calendar days.

    DST repeated hours are combined; missing hours stay empty. Counts weight
    cigarette quantities, not API calls. Weekdays are normalized by occurrences.
    """
    hours = [dict(hour=hour, quantity=0) for hour in range(24)]
    weekdays = [dict(weekday=day, quantity=0, days=0) for day in range(7)]
    for row in rows:
        local = datetime.fromisoformat(row['occurred_at']).astimezone(tz)
        hours[local.hour]['quantity'] += row['quantity']
    for day in daily:
        bucket = weekdays[date.fromisoformat(day['date']).weekday()]
        bucket['quantity'] += day['quantity']
        bucket['days'] += 1
    for bucket in weekdays:
        bucket['average'] = round(bucket['quantity'] / bucket['days'], 2) if bucket['days'] else None
    total = sum(row['quantity'] for row in hours)
    for hour in hours:
        hour['share_percent'] = round(hour['quantity'] * 100 / total, 2) if total else 0
    completed = daily[:-1] if includes_today else daily
    codes = sorted({code for day in completed for code in day['amounts']} or {currency})
    return dict(
        hourly=hours, weekdays=weekdays,
        projection=dict(days=30, sample_days=len(completed),
                        quantity=round(sum(day['quantity'] for day in completed) * 30 / len(completed), 1) if completed else None,
                        costs={code: money(Decimal(sum(day['amounts'].get(code, 0) for day in completed)) * 30 / len(completed), code)
                               for code in codes} if completed else {}))
