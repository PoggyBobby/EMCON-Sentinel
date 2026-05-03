package com.emconsentinel.ui;

import android.content.Context;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.LinearLayout;
import android.widget.TextView;

import com.atak.plugins.impl.PluginLayoutInflater;

import com.emconsentinel.data.AssetLibrary;
import com.emconsentinel.data.RadioBand;
import com.emconsentinel.data.RadioProfile;
import com.emconsentinel.plugin.R;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

/**
 * Tab 1: pick the operator's radio. List of cards (each = one RadioProfile from
 * AssetLibrary), tap to select. Active card shows a green dot.
 *
 * Replaces the old Spinner — vertical card list is the phone idiom and lets
 * each row show name + freq + EIRP without truncation.
 */
public final class TabRadio {

    private final Context pluginContext;
    private final PluginState state;
    private final View root;
    private final LinearLayout container;
    private final List<View> cardViews = new ArrayList<>();
    private final List<RadioProfile> profiles;

    public TabRadio(Context pluginContext, PluginState state) {
        this.pluginContext = pluginContext;
        this.state = state;
        this.profiles = state.library().radioProfiles();

        this.root = PluginLayoutInflater.inflate(pluginContext, R.layout.tab_radio, null);
        this.container = root.findViewById(R.id.radio_card_container);
        buildCards();
        refreshSelection();
    }

    public View view() { return root; }

    private void buildCards() {
        LayoutInflater inflater = LayoutInflater.from(pluginContext);
        for (int i = 0; i < profiles.size(); i++) {
            final RadioProfile p = profiles.get(i);
            View card = PluginLayoutInflater.inflate(pluginContext, R.layout.radio_card, container);
            // PluginLayoutInflater.inflate(..., container) attaches; the last-child is the new one
            View cardView = container.getChildAt(container.getChildCount() - 1);
            TextView title = cardView.findViewById(R.id.radio_card_title);
            TextView subtitle = cardView.findViewById(R.id.radio_card_subtitle);
            title.setText(p.displayName);
            subtitle.setText(buildSubtitle(p));
            cardView.setOnClickListener(v -> {
                state.setActiveProfile(p);
                refreshSelection();
            });
            cardViews.add(cardView);
        }
    }

    private static String buildSubtitle(RadioProfile p) {
        StringBuilder sb = new StringBuilder();
        if (p.bands != null && !p.bands.isEmpty()) {
            RadioBand b = p.bands.get(0);
            sb.append(String.format(Locale.US, "%.0f MHz", b.freqMhz));
            sb.append("  ·  ").append((int) b.eirpDbm).append(" dBm");
            if (b.dutyCycle > 0 && b.dutyCycle < 1) {
                sb.append("  ·  ").append((int) Math.round(b.dutyCycle * 100)).append("% duty");
            }
            if (p.bands.size() > 1) {
                sb.append("  ·  +").append(p.bands.size() - 1).append(" more bands");
            }
        }
        return sb.toString();
    }

    private void refreshSelection() {
        RadioProfile active = state.activeProfile();
        for (int i = 0; i < cardViews.size(); i++) {
            View card = cardViews.get(i);
            boolean selected = active != null && active.id.equals(profiles.get(i).id);
            TextView check = card.findViewById(R.id.radio_card_check);
            check.setVisibility(selected ? View.VISIBLE : View.INVISIBLE);
            card.setBackgroundColor(selected ? 0xFF2A4A2A : 0xFF1F1F1F);
        }
    }
}
