"""Frozen full-axis donor-precision deconvolution candidate.

This package estimates RNA fractions on the supplied complete gene axis.
It does not return cell counts, existence probabilities, or UNKNOWN labels.
"""

__version__ = "0.1.0"
METHOD_ID = "FULL_DONOR_PRECISION"
FROZEN_CORE_SHA256 = "47eaaa4fd87ed5513575cce025592824dcd1f5f8bbfb5f61c83389a3ea9a535d"

from .api import predict

__all__ = ["predict", "METHOD_ID", "FROZEN_CORE_SHA256", "__version__"]
