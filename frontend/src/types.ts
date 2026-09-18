export type Instrument = {
  id: string;
  venue: string;
  currency: string;
  exposure_group: string;
};

export type Dataset = {
  dataset_id: string;
  name: string;
  mode: string;
  start: string;
  end: string;
  row_count: number;
  instruments: Instrument[];
  corporate_actions_status: string;
  interval: string;
  source: string;
  retrieved_at: string;
  availability_basis: string;
  limitations: string[];
};
