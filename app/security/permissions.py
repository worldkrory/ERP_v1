from __future__ import annotations

from functools import wraps
from typing import Callable, ParamSpec, TypeVar

from flask import abort
from flask_login import current_user


P = ParamSpec("P")
R = TypeVar("R")


def require_role(*required_roles: str):
    """
    Exige una sesión activa y al menos uno de los roles requeridos.

    Los superusuarios son aceptados por User.has_role().
    """
    def decorator(view_function: Callable[P, R]) -> Callable[P, R]:
        @wraps(view_function)
        def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
            if not current_user.is_authenticated:
                abort(401)

            if not current_user.is_active or current_user.is_locked:
                abort(403)

            if not current_user.has_role(*required_roles):
                abort(403)

            return view_function(*args, **kwargs)

        return wrapped

    return decorator