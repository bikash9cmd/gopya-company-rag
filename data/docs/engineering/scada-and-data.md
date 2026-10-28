---
title: SCADA and plant data
dept: engineering
owner: SCADA Engineer
updated: 2082-02-20
---

# SCADA and plant data

The SCADA system records every unit's power, water flow, forebay level, bearing temperatures and
intake sediment once a second. A historian keeps one-minute averages for 10 years.

Engineering staff reach the historian over the company VPN. Export data with the historian's report
tool; do not copy the database. Monthly generation reports are produced from the historian on the
first day of every Nepali month and shared with Finance for the NEA energy bill.

If a SCADA reading looks wrong, check the field instrument before changing anything in SCADA, and
log the fault in the maintenance system.
