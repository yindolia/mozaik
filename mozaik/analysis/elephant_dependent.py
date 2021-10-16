try:
    import elephant
except ImportError:
    print("Python Elephant package missing.")


import warnings
import numpy as np
import quantities as pq
from parameters import ParameterSet
from scipy.optimize import curve_fit
from mozaik.storage import queries
from mozaik.analysis.analysis import Analysis
from mozaik.analysis.data_structures import SingleValue, SingleValueList


class CriticalityAnalysis(Analysis):
    """
    Compute distance to criticality as defined in:
    Ma Z., Turrigiano G.G., Wessel R., Hengen K.B. (2019). Cortical Circuit
    Dynamics Are Homeostatically Tuned to Criticality In Vivo, Neuron
    Computes the histogram of population activity per layer and calculates
    the distance to criticality for several intervals.
    Can only be run on spontaneous activity.
    """

    required_parameters = ParameterSet(
        {
            "bin_length": int,  # Length of duration and size bins
        }
    )

    def perform_analysis(self):
        layers = [["V1_Exc_L2/3", "V1_Inh_L2/3"], ["V1_Exc_L4", "V1_Inh_L4"]]
        for layer in layers:
            if not set(layer).issubset(set(self.datastore.sheets())):
                warnings.warn(
                    "Layer %s not part of data store sheets: %s!"
                    % (layer, self.datastore.sheets())
                )
                continue
            # pool all spikes from the layer
            allspikes = []
            for sheet in layer:
                dsv = queries.param_filter_query(
                    self.datastore, sheet_name=sheet, st_name="InternalStimulus"
                )
                segs = dsv.get_segments()
                assert len(segs) == 1
                seg = segs[0]
                stim = dsv.get_stimuli()[0]
                # add spikes from this sheet to the pool
                for st in seg.spiketrains:
                    allspikes.extend(st.magnitude)

            # calculate specific time bin in each segment as in Fontenele2019
            dt = np.mean(np.diff(np.sort(allspikes)))

            # case with no spikes is not taken care off!
            tstart = seg.spiketrains[0].t_start.magnitude
            tstop = seg.spiketrains[0].t_stop.magnitude
            bins = np.arange(tstart, tstop, dt)
            hist, bins = np.histogram(allspikes, bins)

            # find zeros in the histogram
            zeros = np.where(hist == 0)[0]

            # calculate durations of avalanches
            durs = np.diff(zeros) * dt
            durs = durs[durs > dt]

            # calculate sizes of avalanches
            szs = []
            for i in range(len(zeros) - 1):
                szs.append(np.sum(hist[zeros[i] : zeros[i + 1]]))  # .magnitude))
            szs = np.array(szs)
            szs = szs[szs > 0]

            # calculate tau=exponent of size distr
            s_distr, s_bins = self.create_hist(szs, self.parameters.bin_length)
            s_amp, s_slope, s_error_sq, s_error_diff = self.fit_powerlaw_distribution(
                s_bins, s_distr, "size"
            )
            # calculate tau_t=exponent of distr of durations
            d_distr, d_bins = self.create_hist(durs, self.parameters.bin_length)
            d_amp, d_slope, d_error_sq, d_error_diff = self.fit_powerlaw_distribution(
                d_bins, d_distr, "duration"
            )
            print(s_amp)
            print(s_slope)
            print(d_amp)
            print(d_slope)
            # calculate the <S>(D) curve, S=size, D=duration
            [sd_amp, sd_slope], _ = curve_fit(
                f=self.powerlaw, xdata=durs, ydata=szs, p0=[0, 0]
            )

            """
            Create function for processing avalanches

            Measure average event distance in standard deviations
            """

            beta = sd_slope  # for dcc calculation
            error_diff = sum(szs - self.powerlaw(durs, sd_amp, sd_slope))
            error_sq = np.linalg.norm(szs - self.powerlaw(durs, sd_amp, sd_slope))
            crit_dist = np.abs(beta - (-d_slope - 1) / (-s_slope - 1))

            for sheet in layer:
                common_params = {
                    "sheet_name": sheet,
                    "tags": self.tags,
                    "analysis_algorithm": self.__class__.__name__,
                    "stimulus_id": str(stim),
                }
                self.datastore.full_datastore.add_analysis_result(
                    SingleValue(
                        value=crit_dist * pq.dimensionless,
                        value_units=pq.dimensionless,
                        value_name="DistanceToCriticality",
                        **common_params,
                    )
                )
                self.datastore.full_datastore.add_analysis_result(
                    SingleValue(
                        value=dt * pq.s,
                        value_units=pq.s,
                        value_name="AvalancheBinSize",
                        **common_params,
                    )
                )
                self.datastore.full_datastore.add_analysis_result(
                    SingleValueList(
                        values=durs * pq.s,
                        values_unit=pq.s,
                        value_name="AvalancheDurations",
                        **common_params,
                    )
                )
                self.datastore.full_datastore.add_analysis_result(
                    SingleValueList(
                        values=szs * pq.dimensionless,
                        values_unit=pq.dimensionless,
                        value_name="AvalancheSizes",
                        **common_params,
                    )
                )
                self.datastore.full_datastore.add_analysis_result(
                    SingleValue(
                        value=sd_amp * pq.dimensionless,
                        value_units=pq.dimensionless,
                        value_name="SDAmplitude",
                        **common_params,
                    )
                )
                self.datastore.full_datastore.add_analysis_result(
                    SingleValue(
                        value=sd_slope * pq.dimensionless,
                        value_units=pq.dimensionless,
                        value_name="SDSlope",
                        **common_params,
                    )
                )
                self.datastore.full_datastore.add_analysis_result(
                    SingleValue(
                        value=error_sq * pq.dimensionless,
                        value_units=pq.dimensionless,
                        value_name="SDErrorSq",
                        **common_params,
                    )
                )
                self.datastore.full_datastore.add_analysis_result(
                    SingleValue(
                        value=error_diff * pq.dimensionless,
                        value_units=pq.dimensionless,
                        value_name="SDErrorDiff",
                        **common_params,
                    )
                )
                self.datastore.full_datastore.add_analysis_result(
                    SingleValue(
                        value=s_slope * pq.dimensionless,
                        value_units=pq.dimensionless,
                        value_name="SSlope",
                        **common_params,
                    )
                )
                self.datastore.full_datastore.add_analysis_result(
                    SingleValue(
                        value=s_amp * pq.dimensionless,
                        value_units=pq.dimensionless,
                        value_name="SAmplitude",
                        **common_params,
                    )
                )
                self.datastore.full_datastore.add_analysis_result(
                    SingleValueList(
                        values=s_distr * pq.dimensionless,
                        values_unit=pq.dimensionless,
                        value_name="SDistr",
                        **common_params,
                    )
                )
                self.datastore.full_datastore.add_analysis_result(
                    SingleValueList(
                        values=s_bins * pq.dimensionless,
                        values_unit=pq.dimensionless,
                        value_name="SBins",
                        **common_params,
                    )
                )
                self.datastore.full_datastore.add_analysis_result(
                    SingleValue(
                        value=s_error_sq * pq.dimensionless,
                        value_units=pq.dimensionless,
                        value_name="SErrorSq",
                        **common_params,
                    )
                )
                self.datastore.full_datastore.add_analysis_result(
                    SingleValue(
                        value=s_error_diff * pq.dimensionless,
                        value_units=pq.dimensionless,
                        value_name="SErrorDiff",
                        **common_params,
                    )
                )
                self.datastore.full_datastore.add_analysis_result(
                    SingleValue(
                        value=d_slope * pq.dimensionless,
                        value_units=pq.dimensionless,
                        value_name="DSlope",
                        **common_params,
                    )
                )
                self.datastore.full_datastore.add_analysis_result(
                    SingleValue(
                        value=d_amp * pq.dimensionless,
                        value_units=pq.dimensionless,
                        value_name="DAmplitude",
                        **common_params,
                    )
                )
                self.datastore.full_datastore.add_analysis_result(
                    SingleValueList(
                        values=d_distr * pq.s,
                        values_unit=pq.dimensionless,
                        value_name="DDistr",
                        **common_params,
                    )
                )
                self.datastore.full_datastore.add_analysis_result(
                    SingleValueList(
                        values=d_bins * pq.s,
                        values_unit=pq.dimensionless,
                        value_name="DBins",
                        **common_params,
                    )
                )
                self.datastore.full_datastore.add_analysis_result(
                    SingleValue(
                        value=d_error_sq * pq.dimensionless,
                        value_units=pq.dimensionless,
                        value_name="DErrorSq",
                        **common_params,
                    )
                )
                self.datastore.full_datastore.add_analysis_result(
                    SingleValue(
                        value=d_error_diff * pq.dimensionless,
                        value_units=pq.dimensionless,
                        value_name="DErrorDiff",
                        **common_params,
                    )
                )


    def create_hist(self, data, nrbins):
        distr, b = np.histogram(data, bins=nrbins, density=True)
        bs = b[1] - b[0]
        bins = b[:-1] + bs / 2.0
        return distr, bins

    def fit_powerlaw_distribution(self, x, y, img_title=None):
        """
        Parameters
        ----------
        data : 1D numpy array
            Observations from the probability distribution we want to fit
        nrbins : int
            Number of bins in the created histogram
        img_title : str
            Used for debugging. Title of the powerlaw fit figure.

        Returns
        -------
        amp, slope, tau, error

        amp : float
            Amplitude of the powerlaw distribution
        slope : float
            Slope of the powerlaw distribution
        tau : float
            tau = -slope
        error : float
            Mean square error of the fit
        """
        try:
            [amp, slope], _ = curve_fit(
                f=self.powerlaw, xdata=x, ydata=y, p0=[0, 0]
            )
            error_sq = np.linalg.norm(y - self.powerlaw(x, amp, slope))
            error_diff = sum(y - self.powerlaw(x, amp, slope))
            return amp, slope, error_sq, error_diff
        except Exception as e:
            warnings.warn(
                "While fitting the powerlaw distribution, the following exception occured: %s"
                % e
            )
            return 0, 0, 0

    @staticmethod
    def powerlaw(x, amp, slope):
        return amp * np.power(x, slope)

    def debug_plot(self, binss, distr, amp, slope, title):
        import pylab

        fig = pylab.figure()
        ax = pylab.gca()
        ax.plot(binss, self.powerlaw(binss, amp, slope))
        ax.plot(binss, distr, "o")
        ax.set_title(title)
        ax.set_yscale("log")
        ax.set_xscale("log")
        pylab.savefig("%s.png" % title)
        pylab.close()
