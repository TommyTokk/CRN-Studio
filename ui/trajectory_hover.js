// The Streamlit chart owns Plotly rendering; this runtime only reads its events.
(() => {
    const doc = window.parent.document;
    let attempts = 0;
    const install = () => {
        const root = doc.querySelector('.st-key-' + chartKey);
        let panel = root?.querySelector('.trajectory-readout');
        const plot = root?.querySelector('.js-plotly-plot');
        if (!panel || !plot?.on || !plot._fullData) {
            if (attempts++ < 100) window.setTimeout(install, 100);
            return;
        }

        const previous = root.trajectoryHover;
        if (previous?.signature === signature && previous.panel === panel) {
            previous.bind();
            return;
        }
        previous?.dispose();
        let boundPlot = null;
        let boundOn = null;
        let sample = null;
        let disposed = false;
        let body = panel.querySelector('.trajectory-readout-body');
        let time = panel.querySelector('.trajectory-readout-time');
        const format = value => Number.isFinite(value)
            ? Number(value.toPrecision(8)).toString() : '—';

        const render = () => {
            if (sample === null) {
                time.textContent = '';
                body.textContent = payload.species.length
                    ? 'Hover over the chart to inspect concentrations.'
                    : 'Select at least one species to inspect concentrations.';
                return;
            }
            time.textContent = payload.timeLabel + ': ' + format(payload.time[sample]);
            const scroll = panel.scrollTop;
            const rows = doc.createDocumentFragment();
            payload.species.forEach((species, index) => {
                const trace = boundPlot._fullData[index];
                if (!trace || trace.visible === false || trace.visible === 'legendonly') return;
                const row = doc.createElement('div');
                row.className = 'trajectory-readout-row';
                const swatch = doc.createElement('span');
                swatch.className = 'trajectory-readout-swatch';
                swatch.style.borderColor = trace.line.color;
                swatch.setAttribute('aria-hidden', 'true');
                const name = doc.createElement('span');
                name.className = 'trajectory-readout-name';
                name.textContent = species.name;
                const value = doc.createElement('span');
                value.className = 'trajectory-readout-value';
                value.textContent = format(species.values[sample]);
                row.append(swatch, name, value);
                rows.append(row);
            });
            body.replaceChildren(rows);
            panel.scrollTop = scroll;
        };
        const hover = event => {
            const index = event.points?.[0]?.pointNumber;
            if (!Number.isInteger(index) || index < 0 || index >= payload.time.length) return;
            sample = index;
            render();
        };
        const afterPlot = () => render();
        const detach = () => {
            boundPlot?.removeListener?.('plotly_hover', hover);
            boundPlot?.removeListener?.('plotly_afterplot', afterPlot);
        };
        const bind = () => {
            if (disposed) return;
            // Streamlit can replace st.html without reloading the helper iframe.
            const currentPanel = root.querySelector('.trajectory-readout');
            if (!currentPanel) return;
            if (currentPanel !== panel) {
                panel = currentPanel;
                body = panel.querySelector('.trajectory-readout-body');
                time = panel.querySelector('.trajectory-readout-time');
                sample = null;
                root.trajectoryHover.panel = panel;
                panel.querySelector('header strong').textContent = payload.valueLabel;
                render();
            }
            const candidate = root.querySelector('.js-plotly-plot');
            if (!candidate?.on || !candidate._fullData) return;
            if (candidate === boundPlot && candidate.on === boundOn) return;
            detach();
            boundPlot = candidate;
            boundOn = candidate.on;
            boundPlot.on('plotly_hover', hover);
            boundPlot.on('plotly_afterplot', afterPlot);
            render();
        };
        const observer = new MutationObserver(bind);
        observer.observe(root, {childList: true, subtree: true});
        const dispose = () => {
            disposed = true;
            observer.disconnect();
            detach();
        };
        root.trajectoryHover = {signature, panel, bind, dispose};
        panel.querySelector('header strong').textContent = payload.valueLabel;
        bind();
    };
    install();
})();
