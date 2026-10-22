"""Typed input errors. The CLI maps every DCFInputError to exit code 2."""

EXIT_CODE = 2


class DCFInputError(Exception):
    """Base class for refusals and input errors. The message is one clear line."""

    exit_code = EXIT_CODE


class NegativeFCF(DCFInputError):  # noqa: N818
    pass


class FinancialsSector(DCFInputError):  # noqa: N818
    pass


class StaleData(DCFInputError):  # noqa: N818
    pass


class MissingData(DCFInputError):  # noqa: N818
    pass


class CurrencyMismatch(DCFInputError):  # noqa: N818
    """Price currency and financial-statement currency differ."""


class DataUnavailable(DCFInputError):  # noqa: N818
    """A data source failed or returned an unusable payload."""
