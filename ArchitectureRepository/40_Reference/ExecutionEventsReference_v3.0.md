# ExecutionEventsReference_v3.0

# Purpose

Defines the standard execution event lifecycle used throughout the Order
Flow Analysis Platform.

------------------------------------------------------------------------

## Execution Events

  -----------------------------------------------------------------------
  Event                               Description
  ----------------------------------- -----------------------------------
  Order Submitted                     Order accepted by the trading
                                      platform.

  Order Pending                       Awaiting execution or trigger
                                      condition.

  Order Partially Filled              Portion of the requested quantity
                                      has been executed.

  Order Filled                        Entire requested quantity has been
                                      executed.

  Order Cancelled                     Order cancelled before completion.

  Order Rejected                      Order rejected by broker or
                                      exchange.

  Order Expired                       Order expired according to its Time
                                      in Force rule.
  -----------------------------------------------------------------------

------------------------------------------------------------------------

## Event Rules

-   Events shall be recorded in chronological order.
-   Every event shall include a timestamp.
-   Status transitions shall be immutable once recorded.
-   Exchange-specific event types shall extend, not replace, these
    definitions.

Status: Phase4 Reference Enhancement
