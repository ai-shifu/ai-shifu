from flaskr.i18n import _

ORDER_STATUS_INIT = 501
ORDER_STATUS_SUCCESS = 502
ORDER_STATUS_REFUND = 503
ORDER_STATUS_TO_BE_PAID = 504
ORDER_STATUS_TIMEOUT = 505

LEARN_STATUS_NOT_STARTED = 601
LEARN_STATUS_IN_PROGRESS = 602
LEARN_STATUS_COMPLETED = 603
LEARN_STATUS_REFUND = 604
LEARN_STATUS_LOCKED = 605
LEARN_STATUS_UNAVAILABLE = 606
LEARN_STATUS_BRANCH = 607
LEARN_STATUS_RESET = 608
LEARN_STATUS_NOT_EXIST = -1
ORDER_STATUS_TYPES = {
    _("module.backend.order.orderStatusInit"): ORDER_STATUS_INIT,
    _("module.backend.order.orderStatusSuccess"): ORDER_STATUS_SUCCESS,
    _("module.backend.order.orderStatusRefund"): ORDER_STATUS_REFUND,
    _("module.backend.order.orderStatusToBePaid"): ORDER_STATUS_TO_BE_PAID,
    _("module.backend.order.orderStatusTimeout"): ORDER_STATUS_TIMEOUT,
}

ORDER_STATUS_VALUES = {
    ORDER_STATUS_INIT: _("module.backend.order.orderStatusInit"),
    ORDER_STATUS_SUCCESS: _("module.backend.order.orderStatusSuccess"),
    ORDER_STATUS_REFUND: _("module.backend.order.orderStatusRefund"),
    ORDER_STATUS_TO_BE_PAID: _("module.backend.order.orderStatusToBePaid"),
    ORDER_STATUS_TIMEOUT: _("module.backend.order.orderStatusTimeout"),
}

LEARN_STATUS_TYPES = {
    _("module.backend.order.learnStatusNotStarted"): LEARN_STATUS_NOT_STARTED,
    _("module.backend.order.learnStatusInProgress"): LEARN_STATUS_IN_PROGRESS,
    _("module.backend.order.learnStatusCompleted"): LEARN_STATUS_COMPLETED,
    _("module.backend.order.learnStatusRefund"): LEARN_STATUS_REFUND,
    _("module.backend.order.learnStatusLocked"): LEARN_STATUS_LOCKED,
    _("module.backend.order.learnStatusUnavailable"): LEARN_STATUS_UNAVAILABLE,
    _("module.backend.order.learnStatusBranch"): LEARN_STATUS_BRANCH,
    _("module.backend.order.learnStatusReset"): LEARN_STATUS_RESET,
}


def get_learn_status_values():
    return {
        LEARN_STATUS_NOT_STARTED: _("module.backend.order.learnStatusNotStarted"),
        LEARN_STATUS_IN_PROGRESS: _("module.backend.order.learnStatusInProgress"),
        LEARN_STATUS_COMPLETED: _("module.backend.order.learnStatusCompleted"),
        LEARN_STATUS_REFUND: _("module.backend.order.learnStatusRefund"),
        LEARN_STATUS_LOCKED: _("module.backend.order.learnStatusLocked"),
        LEARN_STATUS_UNAVAILABLE: _("module.backend.order.learnStatusUnavailable"),
        LEARN_STATUS_BRANCH: _("module.backend.order.learnStatusBranch"),
        LEARN_STATUS_RESET: _("module.backend.order.learnStatusReset"),
        LEARN_STATUS_NOT_EXIST: _("module.backend.order.learnStatusLocked"),
    }
