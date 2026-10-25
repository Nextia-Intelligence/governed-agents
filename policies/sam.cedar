// The rules for Sam, Blue Kite's support agent, in Cedar.
// The same rules as src/bluekite/governance/policy.py. Tests check that both agree.
// A forbid with @effect("ask") means: not without a person's approval.

// Sam may use its four tools. Everything else is denied by default.
@id("sams-tools-only")
permit (
  principal == Agent::"sam",
  action in [Action::"look_up_order", Action::"change_address",
             Action::"issue_refund", Action::"close_account"],
  resource
);

@id("verified-customer-only")
forbid (principal, action, resource)
unless { context has requester };

@id("own-orders-only")
forbid (
  principal,
  action in [Action::"look_up_order", Action::"issue_refund"],
  resource is Order
)
when { context has requester && resource.owner != context.requester };

@id("own-account-only")
forbid (
  principal,
  action in [Action::"change_address", Action::"close_account"],
  resource is Customer
)
when { context has requester && resource != context.requester };

@id("refund-within-order-total")
forbid (principal, action == Action::"issue_refund", resource is Order)
when { context.amount_cents > resource.refundable_cents };

@id("no-refund-on-closed-account")
forbid (principal, action == Action::"issue_refund", resource is Order)
when { resource.owner_status != "open" };

@id("refund-over-25-needs-human")
@effect("ask")
forbid (principal, action == Action::"issue_refund", resource)
when { context.amount_cents > 2500 };

@id("close-account-needs-human")
@effect("ask")
forbid (principal, action == Action::"close_account", resource);
