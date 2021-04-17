from ...core.utils.py3 import textstring
from ...core.devio import SCPI, interface



class LM500(SCPI.SCPIDevice):
    """
    Cryomagnetics LM500/510 level monitor.

    Channels are enumerated from 1.
    To abort filling or reset a timeout, call :meth:`.SCPIDevice.reset` method.

    Args:
        conn: serial connection parameters (usually port or a tuple containing port and baudrate)
    """
    def __init__(self, conn):
        SCPI.SCPIDevice.__init__(self,conn,backend="serial",term_read="\n",term_write="\n",backend_defaults={"serial":("COM1",9600)})
        try:
            self.write("ERROR 0")
            self.write("REMOTE")
            self._select_channel(1)
        except self.instr.Error:
            self.close()
            raise
        self._add_settings_variable("interval",self.get_interval,self.set_interval,ignore_error=(RuntimeError,))
        self._add_status_variable("level",self.get_level,mux=([1,2],))
        self._add_status_variable("fill_status",self.get_fill_status,mux=([1,2],))
        self._add_settings_variable("high_level",self.get_high_level,self.set_high_level,mux=([1,2],1))
        self._add_settings_variable("low_level",self.get_low_level,self.set_low_level,mux=([1,2],1))

    def close(self):
        """Close connection to the device"""
        try:
            self.write("LOCAL")
        finally:
            SCPI.SCPIDevice.close(self)
    _reset_comm="*RST;REMOTE"

    def _instr_write(self, msg):
        return self.instr.write(msg,read_echo=True,read_echo_delay=0.1)
    def _instr_read(self, raw=False, size=None):
        if size:
            data=self.instr.read(size=size)
        elif raw:
            data=self.instr.readline(remove_term=False)
        else:
            data=""
            while not data:
                data=self.instr.readline(remove_term=True).strip()
        return data

    _p_channel=interface.EnumParameterClass("channel",[1,2])
    def get_channel(self):
        """Get current measurement channel"""
        return self.ask("CHAN?","int")
    @interface.use_parameters
    def set_channel(self, channel=1):
        """Set current measurement channel"""
        self.write("CHAN",channel)
        return self.get_channel()

    _p_channel_type=interface.EnumParameterClass("channel_type",{"lhe":1,"ln":2})
    @interface.use_parameters(_returns="channel_type")
    def get_type(self, channel=1):
        """Get type of a given channel (``"lhe"`` or ``"ln"``)"""
        return self.ask("TYPE? {}".format(channel),"int")
    def _select_channel(self, channel):
        if channel is not None:
            self.write("CHAN",channel)
    def _check_channel_LHe(self, op, channel=None):
        if channel is None:
            channel=self.get_channel()
        if self.get_type(channel)=="ln":
            raise RuntimeError("LN channel doesn't support {}".format(op))
    
    _p_mode=interface.EnumParameterClass("mode",{"sample_hold":"s","continuous":"c"})
    @interface.use_parameters(_returns="mode")
    def get_mode(self, channel=None):
        """
        Get measurement mode at the given channel (``None`` for the currently selected channel).

        Can be either ``'sample_hold'``, or ``'continuous'``.
        """
        self._select_channel(channel)
        self._check_channel_LHe("measurement modes")
        return self.ask("MODE?").upper()
    @interface.use_parameters
    def set_mode(self, mode, channel=None):
        """
        Set measurement mode at the given channel (``None`` for the current channel).

        Can be either ``'sample_hold'``, or ``'continuous'``.
        """
        self._select_channel(channel)
        self._check_channel_LHe("measurement modes")
        self.write("MODE",mode)
        return self.get_mode()

    @staticmethod
    def _str_to_sec(s):
        s=s.strip().split(":")
        s=[int(n.strip()) for n in s]
        return s[0]*60**2+s[1]*60+s[2]
    @staticmethod
    def _sec_to_str(s):
        return "{:02d}:{:02d}:{:02d}".format(s//60**2,(s//60)%60,s%60)
    @interface.use_parameters
    def get_interval(self, channel=None):
        """Get measurement interval (in seconds) in sample/hold mode at the given channel (``None`` for the current channel)"""
        self._select_channel(channel)
        self._check_channel_LHe("measurement intervals")
        return self._str_to_sec(self.ask("INTVL?"))
    @interface.use_parameters
    def set_interval(self, intvl, channel=None):
        """Set measurement interval (in seconds) in sample/hold mode at the given channel (``None`` for the current channel)"""
        self._select_channel(channel)
        self._check_channel_LHe("measurement intervals")
        if not isinstance(intvl,textstring):
            intvl=self._sec_to_str(intvl)
        self.write("INTVL",intvl)
        return self.get_interval()
    
    @interface.use_parameters
    def start_measurement(self, channel=1):
        """Initialize measurement on a given channel"""
        self.write("MEAS",channel)
    def _get_stb(self):
        return self.ask("*STB?","int")
    @interface.use_parameters
    def wait_for_measurement(self, channel=1):
        """Wait for the measurement on a given channel to finish"""
        mask=0x01 if channel==1 else 0x04
        while not self._get_stb()&mask:
            self.sleep(0.1)
    @interface.use_parameters
    def get_level(self, channel=1):
        """Get level reading on a given channel"""
        res=self.ask("MEAS? {}".format(channel))
        return float(res.split()[0])
    @interface.use_parameters
    def measure_level(self, channel=1):
        """Measure the level (perform the measurement and return the result) on a given channel"""
        self.start_measurement(channel=channel)
        self.wait_for_measurement(channel=channel)
        return self.get_level(channel=channel)

    @interface.use_parameters
    def start_fill(self, channel=1):
        """Initialize filling at a given channel (``None`` for the current channel)"""
        self.write("FILL",channel)
    @interface.use_parameters
    def get_fill_status(self, channel=1):
        """
        Get filling status at a given channels (``None`` for the current channel).
        
        Return either ``"off"`` (filling is off), ``"timeout"`` (filling timed out) or a float (time since filling started, in seconds).
        """
        res=self.ask("FILL? {}".format(channel)).lower()
        if res in {"off","timeout"}:
            return res
        spres=res.split()
        if len(spres)==1 or spres[1] in ["m","min"]:
            return float(spres[0])*60.
        if spres[1] in ["s","sec"]:
            return float(spres[0])
        raise ValueError("unexpected response: {}".format(res))

    @interface.use_parameters
    def get_low_level(self, channel=None):
        """Get low level (automated refill start) setting on a given channel (``None`` for the current channel)"""
        self._select_channel(channel)
        return float(self.ask("LOW?").split()[0])
    @interface.use_parameters
    def set_low_level(self, level, channel=None):
        """Set low level (automated refill start) setting on a given channel (``None`` for the current channel)"""
        self._select_channel(channel)
        self.write("LOW",level)
    @interface.use_parameters
    def get_high_level(self, channel=None):
        """Get high level (automated refill stop) setting on a given channel (``None`` for the current channel)"""
        self._select_channel(channel)
        return float(self.ask("HIGH?").split()[0])
    @interface.use_parameters
    def set_high_level(self, level, channel=None):
        """Set high level (automated refill stop) setting on a given channel (``None`` for the current channel)"""
        self._select_channel(channel)
        self.write("HIGH",level)

    # _p_analog_output_channel=interface.EnumParameterClass("source",{"sel":0,1:1,2:2})
    # @interface.use_parameters
    # def set_analog_output_channel(self, source):
    #     """
    #     Select source of the analog output.

    #     Can be a channel number (1 or 2) or ``'sel'``, if the digital input select is used.
    #     """
    #     self.write("OUT",source)
    # @interface.use_parameters(_returns="source")
    # def get_analog_output_channel(self):
    #     """
    #     Get the source of the analog output.

    #     Can be a channel number (1 or 2) or ``'sel'``, if the digital input select is used.
    #     """
    #     self.ask("OUT?","int")