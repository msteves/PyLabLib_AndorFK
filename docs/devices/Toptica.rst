.. _lasers_toptica:

.. note::
    General device communication concepts are described on the corresponding :ref:`page <devices_basics>`.

Toptica iBeam Smart laser
==============================

Toptica iBeam Smart is a series of CW diode lasers from Toptica. The software has been tested with the standard 633nm laser.

The main device class is :class:`pylablib.devices.Toptica.TopticaIBeam<.ibeam.TopticaIBeam>`.


Software requirements
-----------------------

The device is connected to the PC via RS232 or USB. RS232 simply requires a COM-port controller on the PC, which in most cases is a USB-to-Serial adapter. Such adapters normally come with their standard drivers. The USB version simply involves a built-in USB-to-Serial converter (e.g., a standard FTDI chip), so it also shows up as a virtual COM port. Hence, it requires relatively standard drivers, which are either included with the laser, or can be download from the `manufacturer's website <https://www.toptica.com/products/single-mode-diode-lasers/ibeam-smart/>`__, for example, together with the TOPAS control software.


Connection
-----------------------

Since the devices are identified as virtual COM ports, they use the standard :ref:`connection method <devices_connection>`, and all you need to know is their COM-port address (e.g., ``COM5``) and, possibly, baud rate, if it is different from the standard 115200 baud::

    >> from pylablib.devices import Toptica
    >> laser1 = Toptica.TopticaIBeam("COM5")
    >> laser2 = Toptica.TopticaIBeam(("COM10",38400))  # in case of 38400 baud connection
    >> laser1.close()
    >> laser2.close()


Operation
-----------------------

Power and output control
~~~~~~~~~~~~~~~~~~~~~~~~

Usually the laser has the main power control and one or several (up to 5) output channels, which can be controlled separately. To turn the whole laser on or off, you can use :meth:`.TopticaIBeam.enable`, while each channel is controlled using :meth:`.TopticaIBeam.enable_channel`. The power is set independently for each channel via :meth:`.TopticaIBeam.set_channel_power`. The actual output power can be queried using :meth:`.TopticaIBeam.get_output_power`.

Detailed info
~~~~~~~~~~~~~~~~~~~~~~~~

The most detailed information about the laser can be obtained using :meth:`.TopticaIBeam.get_full_data` method. It outputs a detailed report generated by the laser, which contains most of the adjustable parameters.

Notes and issues
~~~~~~~~~~~~~~~~~~~~~~~~

Occasionally the laser communication falls into an error state, where replies are lagging behind the requests (i.e., instead of replying to the issued command, the devices replies to the previous one). This is especially likely if several commands are issued in a rapid succession. If this happens, the laser should be rebooted using :meth:`.TopticaIBeam.reboot` method.