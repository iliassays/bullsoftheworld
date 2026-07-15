import { Plus, Sparkles, X } from "lucide-react";
import { useEffect, useState } from "react";
import {
  Dialog,
  DialogTrigger,
  Heading,
  Modal,
  ModalOverlay,
  TextArea,
} from "react-aria-components";

import { Button, IconButton, SelectField } from "../../design-system";
import type { ResearchMarket } from "./model";

export function StartResearchDialog({
  defaultMarket,
  onStage,
}: {
  defaultMarket: ResearchMarket;
  onStage: (request: { market: ResearchMarket; question: string }) => void;
}) {
  const [market, setMarket] = useState<ResearchMarket>(defaultMarket);
  const [question, setQuestion] = useState("");

  useEffect(() => setMarket(defaultMarket), [defaultMarket]);

  return (
    <DialogTrigger>
      <Button variant="primary">
        <Plus aria-hidden="true" size={15} />
        New research
      </Button>
      <ModalOverlay className="ds-modal-overlay" isDismissable>
        <Modal className="ds-modal">
          <Dialog aria-label="Start a research request" className="research-request-dialog">
            {({ close }) => (
              <form
                onSubmit={(event) => {
                  event.preventDefault();
                  const trimmed = question.trim();
                  if (!trimmed) return;
                  onStage({ market, question: trimmed });
                  setQuestion("");
                  close();
                }}
              >
                <header className="research-request-dialog__header">
                  <span className="research-request-dialog__icon">
                    <Sparkles aria-hidden="true" size={18} />
                  </span>
                  <span>
                    <Heading slot="title">Start a research run</Heading>
                    <p>The planner will build an evidence pack before drafting conclusions.</p>
                  </span>
                  <IconButton label="Close" onPress={close}>
                    <X aria-hidden="true" size={17} />
                  </IconButton>
                </header>
                <div className="research-request-dialog__body">
                  <label htmlFor="research-question">Research question</label>
                  <TextArea
                    autoFocus
                    className="research-request-dialog__textarea"
                    id="research-question"
                    onChange={(event) => setQuestion(event.currentTarget.value)}
                    placeholder="e.g. Which small-cap names have a confirmed catalyst, sufficient runway, and no unresolved dilution risk?"
                    rows={5}
                    value={question}
                  />
                  <div className="research-request-dialog__settings">
                    <span>
                      <label>Market scope</label>
                      <SelectField
                        label="Market scope"
                        onChange={setMarket}
                        options={[
                          { value: "US", label: "United States" },
                          { value: "DSE", label: "Dhaka Stock Exchange" },
                        ]}
                        value={market}
                      />
                    </span>
                    <span>
                      <label>Knowledge cutoff</label>
                      <strong>Latest verified evidence</strong>
                    </span>
                  </div>
                </div>
                <footer className="research-request-dialog__footer">
                  <span>Preview mode stages the request locally.</span>
                  <div>
                    <Button onPress={close} variant="quiet">
                      Cancel
                    </Button>
                    <Button isDisabled={!question.trim()} type="submit" variant="primary">
                      Stage research
                    </Button>
                  </div>
                </footer>
              </form>
            )}
          </Dialog>
        </Modal>
      </ModalOverlay>
    </DialogTrigger>
  );
}
