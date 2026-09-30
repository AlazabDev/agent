"""Frappe compatibility hooks for the Agent package.

The Agent project is primarily a standalone service/CLI, but it can also be
registered in a Frappe site's installed_apps list. Frappe imports
``<app>.hooks`` during migrations, so this module intentionally provides the
minimal app metadata required for that lifecycle without coupling Agent's
runtime to Frappe internals.
"""

app_name = "agent"
app_title = "Agent"
app_publisher = "AlazabDev"
app_description = "Agent runtime and automation services for the Alazab Frappe environment"
app_email = "dev@alazab.com"
app_license = "MIT"

# Keep the compatibility layer deliberately minimal. Agent does not currently
# register DocType hooks, scheduler events, fixtures, or migration callbacks.
