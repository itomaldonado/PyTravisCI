"""
Just another Travis CI (API) Python interface.

A module which provides the base of all communicator.

Author:
    Nissar Chababy, @funilrys, contactTATAfunilrysTODTODcom

Project link:
    https://github.com/funilrys/PyTravisCI

Project documentation:
    https://pytravisci.readthedocs.io/en/latest/

License
::


    MIT License

    Copyright (c) 2019, 2020 Nissar Chababy

    Permission is hereby granted, free of charge, to any person obtaining a copy
    of this software and associated documentation files (the "Software"), to deal
    in the Software without restriction, including without limitation the rights
    to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
    copies of the Software, and to permit persons to whom the Software is
    furnished to do so, subject to the following conditions:

    The above copyright notice and this permission notice shall be included in all
    copies or substantial portions of the Software.

    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
    IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
    FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
    AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
    LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
    OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
    SOFTWARE.
"""

import inspect
import urllib.parse as urllib_parse
from functools import wraps
from typing import Any, Optional, Union

import PyTravisCI.exceptions as exceptions
import PyTravisCI.standardization as standardization
from PyTravisCI.requester import Requester


class CommunicatorBase:
    """
    Provides the base of all communicator.
    """

    resource_types: Optional["resource_types._all"] = None
    requester: Optional[Requester] = None
    standardizer: Optional[standardization.Standardization] = None

    endpoints: dict = dict()
    """
    Should be a :py:class:`dict` in format:

    ::

        {
            "from_id": "/build/%(build_id)s"
        }

    :code:`from_id` is the name of the method and
    :code:`build/%(build_id)s` is the endpoint we need
    to communicate with. :code:`%(build_id)s` is what
    the method will expect as variable name. In fact,
    if the end-user give us :code:`build_id=4` as argument,
    the system will replace :code:`%(build_id)s` with :code:`4`.
    """

    def __init__(self, req: Requester) -> None:
        if not isinstance(req, Requester):
            raise TypeError(f"<requester> must be {Requester}. {type(req)} given.")

        # pylint: disable=import-outside-toplevel
        import PyTravisCI.resource_types._all as resource_types

        self.resource_types = resource_types
        self.requester = req
        self.standardizer = standardization.Standardization()

    def complete_response(func):  # pylint: disable=no-self-argument
        """
        A decorator which complete the responses before giving it back
        to the end-user.
        """

        @wraps(func)
        def wrapper(self, **kwargs):
            response = func(self, **kwargs)  # pylint:disable=not-callable

            ignore_sharing = [
                "parameters",
                "data",
            ]

            if hasattr(response, "_at_type"):
                to_propagate = {
                    "_PyTravisCI": {
                        "com": {},
                        "shared": {
                            x: y for x, y in kwargs.items() if x not in ignore_sharing
                        },
                    }
                }

                try:
                    to_propagate["_PyTravisCI"]["com"]["requester"] = self.requester
                except AttributeError:
                    # pylint: disable=protected-access
                    to_propagate["_PyTravisCI"]["com"]["requester"] = self._PyTravisCI[
                        "com"
                    ]["requester"]

                response = CommunicatorBase.propagate_vars(to_propagate, response)
            return response

        return wrapper

    def filter_before_action(func):  # pylint: disable=no-self-argument
        """
        A decorator which filter/format the given arguments
        before giving it back to the communicator method.

        This is useful in order to avoid having the same thing over
        and over everywhere.
        """

        @wraps(func)
        def wrapper(self, **kwargs):

            if "repository_id_or_slug" in kwargs:
                kwargs["repository_id_or_slug"] = self.encode_slug(
                    kwargs["repository_id_or_slug"]
                )

            return func(self, **kwargs)  # pylint: disable=not-callable

        return wrapper

    @classmethod
    def propagate_vars(cls, variables: dict, start_obj: object) -> object:
        """
        Propagate the given var to all objects.
        """

        for var_name, var_value in variables.items():
            if hasattr(start_obj, var_name):
                if isinstance(var_value, dict):
                    start_obj[var_name].update(var_value)
                else:
                    start_obj[var_name] = var_value
            else:
                start_obj[var_name] = var_value

        try:
            for _, value in start_obj.__dict__.items():
                if hasattr(value, "_at_type"):
                    value = cls.propagate_vars(variables, value)
                elif isinstance(value, list):
                    value = [cls.propagate_vars(variables, x) for x in value]
        except AttributeError:
            pass
        return start_obj

    @classmethod
    def is_digit(cls, data: Union[str, int]) -> bool:
        """
        Checks if the given data is an integer or a digit string.
        """

        return isinstance(data, int) or (isinstance(data, str) and data.isdigit())

    @classmethod
    def encode_slug(cls, slug: str) -> str:
        """
        Encodes the (repository) slug.
        """

        if slug and not cls.is_digit(slug) and "%" not in slug:
            slug = urllib_parse.quote(slug, safe="")

        return slug

    @classmethod
    def get_method_name(cls) -> str:
        """
        Provides the method name.
        """

        return inspect.getouterframes(inspect.currentframe(), 2)[2][3]

    def get_standardized(self, data: dict) -> Any:
        """
        Provides the standardized version of the given dataset.
        """

        try:
            self.standardizer.set_data(data)
            return self.standardizer.get_standized()
        except AttributeError:
            return data

    def get_response(self, endpoint: str) -> dict:
        """
        Provides the response from the API.
        """

        return self.requester.get(endpoint)

    def post_response(self, endpoint: str, data: dict = None) -> dict:
        """
        POST and provides the response from the API.
        """

        return self.requester.post(endpoint, data=data)

    def patch_response(self, endpoint: str, data: dict = None) -> dict:
        """
        PATCH and provides the response from the API.
        """

        return self.requester.patch(endpoint, data=data)

    def delete_response(self, endpoint: str) -> Union[dict, bool]:
        """
        DELETE and provides the response from the API.
        """

        try:
            return self.requester.delete(endpoint)
        except exceptions.TravisCIError as exception:
            response_info = exception.get_response()
            if "status_code" in response_info and response_info["status_code"] == 204:
                return True
            return False

    def get_and_construct_endpoint(self, kwargs: dict) -> str:
        """
        Provides the endpoint to call from the given method name.
        """

        if "parameters" in kwargs and kwargs["parameters"]:
            params = urllib_parse.urlencode(kwargs["parameters"].copy())

            del kwargs["parameters"]

            if params:
                return self.endpoints[self.get_method_name()] % kwargs + f"?{params}"
        return self.endpoints[self.get_method_name()] % kwargs
